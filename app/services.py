from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urlparse

from app.engine import BrowserManager, ContentExtractor, PageInteractor
from app.engine.adapters import GenericAdapter, STATS_ADAPTERS
from app.engine.adapters.base_adapter import BaseAdapter
from app.filters import apply_category_filters
from app.models.scrape_result import ScrapeResult
from app.export import Exporter

logger = logging.getLogger("scraper.services")


class ScraperService:
    def __init__(self) -> None:
        self.browser = BrowserManager()
        self.adapter = GenericAdapter()
        self.exporter = Exporter()
        # Adapter dedicati (siti di statistiche) prima del generico: vengono
        # scelti per dominio da _select_adapter; il generico è il fallback.
        self._adapters: list[BaseAdapter] = [*STATS_ADAPTERS, GenericAdapter()]
        self._current_page = None

    def register_adapter(self, adapter: BaseAdapter) -> None:
        self._adapters.insert(0, adapter)

    def _select_adapter(self, url: str) -> BaseAdapter:
        for adapter in self._adapters:
            if adapter.matches(url):
                return adapter
        return self._adapters[-1]

    async def scrape(
        self,
        url: str,
        keywords: list[str] | None = None,
        category: str | None = None,
        filters: dict | None = None,
        headless: bool = True,
        wait_for: str | None = None,
        interactions: list[dict] | None = None,
        screenshot: bool = False,
    ) -> ScrapeResult:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        filters = filters or {}

        try:
            await self.browser.start(headless=headless)
            page = await self.browser.new_page()
            self._current_page = page

            logger.info("Navigo a: %s (categoria: %s)", url, category or "generica")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Best-effort: lascia stabilizzare le richieste di rete (SPA, lazy load).
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                logger.debug("networkidle non raggiunto, proseguo")

            wait_sel = wait_for or filters.get("wait_for", "")
            if wait_sel:
                try:
                    await page.wait_for_selector(wait_sel, timeout=10000)
                except Exception:
                    logger.warning("Selector '%s' non trovato, proseguo", wait_sel)

            if interactions:
                interactor = PageInteractor(page)
                for action in interactions:
                    await self._execute_interaction(interactor, action)

            # Scroll automatico: molti siti (social, e-commerce, news) caricano
            # i contenuti in modo lazy mentre si scorre. Senza questo otterremmo
            # solo la prima schermata.
            await self._auto_scroll(page)

            final_url = page.url
            adapter = self._select_adapter(url)
            # Estrai tutto: il filtraggio per categoria avviene dopo, in modo
            # che ogni filtro "cozzi" davvero con i dati estratti.
            result = await adapter.scrape(page, url, None)
            raw_count = len(result.items)
            challenge_blob = (result.title or "") + " " + " ".join(
                str(i.content) for i in result.items[:8]
            )
            result = apply_category_filters(result, category, filters, keywords)

            # Avviso utile quando un sito restituisce pochi dati (tipicamente
            # social/pagine dietro login o contenuti caricati solo dopo l'accesso).
            result.notice = self._build_notice(
                url, final_url, category, raw_count, challenge_blob
            )

            if screenshot:
                ss_path = await self.browser.screenshot(page)
                result.screenshots.append(ss_path)

            return result

        except Exception as e:
            logger.error("Scraping fallito: %s", e, exc_info=True)
            return ScrapeResult(
                url=url,
                error=f"Errore durante lo scraping: {str(e)}",
            )

    async def _auto_scroll(self, page, rounds: int = 5) -> None:
        """Scorre la pagina per innescare il caricamento lazy dei contenuti."""
        try:
            interactor = PageInteractor(page)
            last_height = 0
            for _ in range(rounds):
                await interactor.scroll_to_bottom()
                height = await page.evaluate("document.body.scrollHeight")
                if height == last_height:
                    break  # niente di nuovo da caricare
                last_height = height
        except Exception as e:
            logger.debug("Auto-scroll interrotto: %s", e)

    # Domini social che, da non loggati, mostrano quasi sempre solo i dati pubblici.
    _SOCIAL_DOMAINS = ("instagram", "facebook", "twitter", "x.com", "tiktok", "linkedin", "threads")
    # Siti di statistiche protetti da Cloudflare / resi via JavaScript.
    _STATS_DOMAINS = ("soccerstats", "footystats", "sofascore")

    _CHALLENGE_MARKERS = (
        "just a moment", "checking your browser", "verifica di sicurezza",
        "verifica riuscita", "verifying you are human", "enable javascript and cookies",
        "controllo del browser", "needs to review the security",
    )

    def _build_notice(
        self, url: str, final_url: str, category: str | None,
        raw_count: int, challenge_blob: str = "",
    ) -> str | None:
        domain = urlparse(final_url or url).netloc.lower()
        is_social = any(d in domain for d in self._SOCIAL_DOMAINS)
        is_stats = any(d in domain for d in self._STATS_DOMAINS)
        looks_login = any(k in (final_url or "").lower() for k in ("login", "signin", "accedi", "/auth", "authwall"))
        challenged = any(m in challenge_blob.lower() for m in self._CHALLENGE_MARKERS)

        if challenged:
            return (
                "Il sito è protetto da Cloudflare e ha mostrato una verifica anti-bot "
                "che il browser automatico non è riuscito a superare. Riprova (a volte "
                "passa al secondo tentativo) oppure apri prima il sito manualmente. "
                "I siti con verifica interattiva non sono sempre estraibili in automatico."
            )

        if is_stats and raw_count == 0:
            return (
                "Il sito di statistiche non ha restituito dati: probabilmente Cloudflare "
                "ha bloccato la richiesta o i contenuti non si sono caricati in tempo. "
                "Riprova (il challenge spesso passa al secondo tentativo) o usa l'URL di una "
                "pagina specifica (es. classifica del campionato)."
            )

        if is_social and raw_count == 0:
            return (
                "Il social non ha restituito contenuti pubblici per questo URL: "
                "probabilmente richiede il login oppure ha bloccato la richiesta. "
                "Prova con l'URL di un post o profilo pubblico (es. .../p/CODICE/)."
            )
        if is_social and (looks_login or raw_count <= 6):
            return (
                "Questo social mostra i contenuti completi solo dopo il login. "
                "Sono stati estratti i dati pubblici disponibili (anteprima OpenGraph, "
                "meta tag, dati strutturati e testo visibile). Per i feed/profili privati "
                "non è possibile estrarre di più senza autenticazione."
            )
        if looks_login:
            return (
                "Il sito sembra aver reindirizzato a una pagina di login: estratti solo "
                "i dati pubblici. Prova un URL accessibile senza autenticazione."
            )
        if raw_count == 0:
            return (
                "Nessun contenuto estratto: il sito potrebbe caricare i dati dinamicamente, "
                "bloccare i bot o richiedere il login. Prova ad aumentare l'attesa o un altro URL."
            )
        return None

    async def _execute_interaction(self, interactor: PageInteractor, action: dict) -> None:
        action_type = action.get("type", "").lower()
        selector = action.get("selector", "")
        value = action.get("value", "")

        handlers = {
            "click": lambda: interactor.click(selector),
            "fill": lambda: interactor.fill(selector, value),
            "select": lambda: interactor.select_option(selector, value),
            "scroll_down": lambda: interactor.scroll_down(int(value or 500)),
            "scroll_to": lambda: interactor.scroll_into_view(selector),
            "hover": lambda: interactor.hover(selector),
            "wait": lambda: interactor.wait_for_selector(selector),
        }

        handler = handlers.get(action_type)
        if handler:
            await handler()

    async def export(self, result: ScrapeResult, name: str = "scrape_result", fmt: str = "json") -> str:
        from app.models.scrape_result import ExportFormat
        fmt_map = {
            "json": ExportFormat.JSON,
            "csv": ExportFormat.CSV,
            "xlsx": ExportFormat.EXCEL,
        }
        return self.exporter.export(result, name, fmt_map.get(fmt, ExportFormat.JSON))

    async def export_all(self, result: ScrapeResult, name: str = "scrape_result") -> dict[str, str]:
        """Esporta il risultato in tutti i formati (JSON, CSV, Excel)."""
        return self.exporter.export_all(result, name)

    @property
    def output_dir(self) -> str:
        return str(self.exporter.output_dir.resolve())

    async def close(self) -> None:
        await self.browser.close()
        self._current_page = None

    @property
    def current_page(self):
        return self._current_page
