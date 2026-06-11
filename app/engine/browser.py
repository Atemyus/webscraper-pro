from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

# patchright è un drop-in di Playwright "non rilevabile": nasconde i segnali di
# automazione (CDP) che Cloudflare Turnstile usa. Se disponibile lo proviamo per
# primo, ma manteniamo SEMPRE Playwright normale come riserva (così l'app parte
# anche se i browser di patchright non sono installati).
from playwright.async_api import async_playwright as _pw_playwright, Page, Browser

try:
    from patchright.async_api import async_playwright as _patchright_playwright  # type: ignore
    _HAS_PATCHRIGHT = True
except Exception:  # pragma: no cover
    _patchright_playwright = None
    _HAS_PATCHRIGHT = False

logger = logging.getLogger("scraper.engine")

# Canali (browser di sistema) da provare, in ordine. msedge c'è su ogni Windows.
_CHANNELS = ("chrome", "msedge", None)


def parse_proxy(raw: str | None = None) -> dict | None:
    """Legge un proxy da argomento o da env (SCRAPER_PROXY / HTTPS_PROXY).

    Formato: ``http://user:pass@host:port`` oppure ``host:port``.
    Ritorna il dict proxy nel formato atteso da Playwright, o None.
    """
    raw = raw or os.environ.get("SCRAPER_PROXY") or os.environ.get("HTTPS_PROXY")
    if not raw:
        return None
    from urllib.parse import urlparse
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    if not parsed.hostname:
        return None
    proxy: dict = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}"}
    if parsed.username:
        proxy["username"] = parsed.username
    if parsed.password:
        proxy["password"] = parsed.password
    return proxy


# Patch di stealth applicato a ogni pagina: nasconde i segnali tipici di un
# browser automatizzato che Cloudflare & co. usano per rilevare i bot.
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['it-IT','it','en-US','en'] });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
window.chrome = window.chrome || { runtime: {}, app: {}, csi: function(){}, loadTimes: function(){} };
const _q = window.navigator.permissions && window.navigator.permissions.query;
if (_q) {
  window.navigator.permissions.query = (p) => (
    p && p.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : _q(p)
  );
}
try {
  const gp = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';            // UNMASKED_VENDOR_WEBGL
    if (p === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
    return gp.call(this, p);
  };
} catch (e) {}
"""


class BrowserManager:
    _instance: Optional[BrowserManager] = None
    _browser: Optional[Browser] = None

    def __new__(cls) -> BrowserManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._playwright = None
        self._browser = None
        self._context = None
        self._channel = None
        self._screenshot_dir = Path(".screenshots")
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def start(self, headless: bool = True) -> None:
        self._headless = headless
        if self._use_persistent():
            if self._browser is not None:  # cambio modalità: chiudi il browser semplice
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            await self._ensure_persistent(headless)
        else:
            if self._context is not None:  # cambio modalità: chiudi il profilo
                try:
                    await self._context.close()
                except Exception:
                    pass
                self._context = None
            await self._ensure_browser(headless)

    def _use_persistent(self) -> bool:
        """Profilo persistente (browser reale + cookie su disco) per superare
        Turnstile: attivo quando l'utente sceglie "Mostra browser"."""
        try:
            from app import config
            return config.get_show_browser()
        except Exception:
            return False

    def _backends(self):
        out = []
        if _HAS_PATCHRIGHT:
            out.append(("patchright", _patchright_playwright))
        out.append(("playwright", _pw_playwright))
        return out

    @staticmethod
    def _args(backend: str) -> list[str]:
        if backend == "patchright":
            return ["--no-sandbox", "--disable-dev-shm-usage"]
        return [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-dev-shm-usage",
        ]

    def is_patchright(self) -> bool:
        return getattr(self, "_backend", None) == "patchright"

    async def _ensure_browser(self, headless: bool) -> None:
        if self._browser is not None and getattr(self, "_browser_headless", None) == headless:
            return
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        last_err = None
        # Prova patchright (anti-Turnstile), poi Playwright normale come riserva;
        # per ciascuno prova Chrome reale, Edge (presente su Windows), poi Chromium.
        for backend, pwmod in self._backends():
            try:
                pw = await pwmod().start()
            except Exception as e:
                last_err = e
                continue
            args = self._args(backend)
            for channel in _CHANNELS:
                try:
                    self._browser = await pw.chromium.launch(
                        headless=headless, channel=channel, args=args)
                    self._playwright, self._backend = pw, backend
                    self._channel = channel or "chromium"
                    self._browser_headless = headless
                    logger.info("Browser: %s (%s)", backend, self._channel)
                    return
                except Exception as e:
                    last_err = e
            try:
                await pw.stop()
            except Exception:
                pass
        raise RuntimeError(f"Avvio browser fallito: {last_err}")

    async def _ensure_persistent(self, headless: bool) -> None:
        if self._context is not None and getattr(self, "_ctx_headless", None) == headless:
            return
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        profile = Path.home() / ".webscraper_pro" / "chrome_profile"
        profile.mkdir(parents=True, exist_ok=True)
        proxy = parse_proxy()
        last_err = None
        for backend, pwmod in self._backends():
            try:
                pw = await pwmod().start()
            except Exception as e:
                last_err = e
                continue
            kwargs: dict = dict(user_data_dir=str(profile), headless=headless,
                                args=self._args(backend), locale="it-IT",
                                timezone_id="Europe/Rome", ignore_https_errors=True,
                                no_viewport=True)
            if proxy:
                kwargs["proxy"] = proxy
            for channel in _CHANNELS:
                try:
                    self._context = await pw.chromium.launch_persistent_context(
                        channel=channel, **kwargs)
                    self._playwright, self._backend = pw, backend
                    self._channel = channel or "chromium"
                    self._ctx_headless = headless
                    logger.info("Profilo persistente: %s (%s)", backend, self._channel)
                    return
                except Exception as e:
                    last_err = e
            try:
                await pw.stop()
            except Exception:
                pass
        raise RuntimeError(f"Avvio profilo persistente fallito: {last_err}")

    async def new_page(
        self,
        user_agent: Optional[str] = None,
        viewport: dict[str, int] | None = None,
    ) -> Page:
        if self._browser is None and self._context is None:
            await self.start(getattr(self, "_headless", True))

        # Modalità profilo persistente: riusa la pagina del profilo (cookie/cf_clearance
        # restano su disco → la verifica Cloudflare si risolve una volta sola).
        if self._context is not None:
            pages = self._context.pages
            page = pages[0] if pages else await self._context.new_page()
            if not self.is_patchright():
                try:
                    await page.add_init_script(_STEALTH_JS)
                except Exception:
                    pass
            return page

        ctx_kwargs: dict = dict(
            viewport=viewport or {"width": 1366, "height": 900},
            locale="it-IT",
            timezone_id="Europe/Rome",
            java_script_enabled=True,
            ignore_https_errors=True,
        )
        if not self.is_patchright():
            ctx_kwargs["user_agent"] = (
                user_agent
                or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        elif user_agent:
            ctx_kwargs["user_agent"] = user_agent

        proxy = parse_proxy()
        if proxy:
            ctx_kwargs["proxy"] = proxy
            logger.info("Uso proxy: %s", proxy["server"])
        context = await self._browser.new_context(**ctx_kwargs)
        page = await context.new_page()
        if not self.is_patchright():
            await page.add_init_script(_STEALTH_JS)
        return page

    async def screenshot(self, page: Page, name: str = "page") -> str:
        path = str(self._screenshot_dir / f"{name}_{id(page)}.png")
        await page.screenshot(path=path, full_page=True)
        return path

    async def close(self) -> None:
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Browser chiuso")

    @classmethod
    async def cleanup(cls) -> None:
        if cls._instance:
            await cls._instance.close()
            cls._instance = None
