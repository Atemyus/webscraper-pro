from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urlparse

from app.engine import BrowserManager, ContentExtractor, PageInteractor
from app.engine.adapters import GenericAdapter
from app.engine.adapters.base_adapter import BaseAdapter
from app.models.scrape_result import ScrapeResult
from app.export import Exporter

logger = logging.getLogger("scraper.services")


class ScraperService:
    def __init__(self) -> None:
        self.browser = BrowserManager()
        self.adapter = GenericAdapter()
        self.exporter = Exporter()
        self._adapters: list[BaseAdapter] = [GenericAdapter()]
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
            await page.goto(url, wait_until="networkidle", timeout=30000)

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

            max_items = int(filters.get("max_items", "0")) if filters.get("max_items") else 0
            adapter = self._select_adapter(url)
            result = await adapter.scrape(page, url, keywords)

            if max_items > 0 and len(result.items) > max_items:
                result.items = result.items[:max_items]

            if filters.get("include_images") is False:
                result.items = [i for i in result.items if i.type != "image"]
            if filters.get("include_links") is False:
                result.items = [i for i in result.items if i.type != "link"]

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

    async def close(self) -> None:
        await self.browser.close()
        self._current_page = None

    @property
    def current_page(self):
        return self._current_page
