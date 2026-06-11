from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

# patchright è un drop-in di Playwright "non rilevabile": nasconde i segnali di
# automazione (CDP) che Cloudflare Turnstile usa per bloccare i browser pilotati.
# Se installato lo usiamo, altrimenti si ripiega su Playwright normale.
try:
    from patchright.async_api import async_playwright  # type: ignore
    from playwright.async_api import Page, Browser
    _USING_PATCHRIGHT = True
except Exception:  # pragma: no cover
    from playwright.async_api import async_playwright, Page, Browser
    _USING_PATCHRIGHT = False

logger = logging.getLogger("scraper.engine")


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
        self._channel = None
        self._screenshot_dir = Path(".screenshots")
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def start(self, headless: bool = True) -> None:
        # Se il browser è già avviato ma in una modalità diversa (es. l'utente ha
        # attivato "mostra browser"), riavvialo nella modalità richiesta.
        if self._browser is not None:
            if getattr(self, "_headless", headless) == headless:
                return
            await self.close()
        self._headless = headless
        self._playwright = await async_playwright().start()
        if _USING_PATCHRIGHT:
            # Con patchright NON usare flag di automazione (sono essi stessi un
            # segnale): lo stealth è gestito internamente.
            args = ["--no-sandbox", "--disable-dev-shm-usage"]
            logger.info("Modalità stealth: patchright attivo")
        else:
            args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-dev-shm-usage",
            ]
        # Chrome reale (channel="chrome") è molto meno rilevabile di Chromium per
        # i challenge Cloudflare. Se non installato, si ripiega su Chromium.
        for channel in ("chrome", None):
            try:
                self._browser = await self._playwright.chromium.launch(
                    headless=headless, channel=channel, args=args,
                )
                self._channel = channel or "chromium"
                break
            except Exception as e:
                logger.debug("Launch channel=%s fallito: %s", channel, e)
        if self._browser is None:
            self._browser = await self._playwright.chromium.launch(headless=headless, args=args)
            self._channel = "chromium"
        logger.info("Browser avviato (%s)", self._channel)

    async def new_page(
        self,
        user_agent: Optional[str] = None,
        viewport: dict[str, int] | None = None,
    ) -> Page:
        if self._browser is None:
            await self.start()
        ctx_kwargs: dict = dict(
            viewport=viewport or {"width": 1366, "height": 900},
            locale="it-IT",
            timezone_id="Europe/Rome",
            java_script_enabled=True,
            ignore_https_errors=True,
        )
        # Con patchright/Chrome reale conviene NON forzare uno user-agent finto
        # (UA Windows su Linux è un segnale): si usa quello reale del browser.
        if not _USING_PATCHRIGHT:
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
        # Le patch JS manuali sono rilevabili: applicale solo SENZA patchright.
        if not _USING_PATCHRIGHT:
            await page.add_init_script(_STEALTH_JS)
        return page

    async def screenshot(self, page: Page, name: str = "page") -> str:
        path = str(self._screenshot_dir / f"{name}_{id(page)}.png")
        await page.screenshot(path=path, full_page=True)
        return path

    async def close(self) -> None:
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
