from __future__ import annotations

import asyncio
import logging
from typing import Optional

from playwright.async_api import Page, Locator

logger = logging.getLogger("scraper.interactor")


class PageInteractor:
    def __init__(self, page: Page):
        self.page = page

    async def click(self, selector: str, timeout: int = 5000) -> bool:
        try:
            locator = self._resolve_locator(selector)
            await locator.first.click(timeout=timeout)
            await self.page.wait_for_timeout(500)
            return True
        except Exception as e:
            logger.warning("Click fallito su '%s': %s", selector, e)
            return False

    async def fill(self, selector: str, value: str, timeout: int = 5000) -> bool:
        try:
            locator = self._resolve_locator(selector)
            await locator.first.fill(value, timeout=timeout)
            return True
        except Exception as e:
            logger.warning("Fill fallito su '%s': %s", selector, e)
            return False

    async def select_option(self, selector: str, value: str, timeout: int = 5000) -> bool:
        try:
            locator = self._resolve_locator(selector)
            await locator.first.select_option(value, timeout=timeout)
            return True
        except Exception as e:
            logger.warning("Select fallito su '%s': %s", selector, e)
            return False

    async def scroll_into_view(self, selector: str, timeout: int = 5000) -> bool:
        try:
            locator = self._resolve_locator(selector)
            await locator.first.scroll_into_view_if_needed(timeout=timeout)
            await self.page.wait_for_timeout(300)
            return True
        except Exception as e:
            logger.warning("Scroll fallito su '%s': %s", selector, e)
            return False

    async def scroll_down(self, pixels: int = 500) -> None:
        await self.page.evaluate(f"window.scrollBy(0, {pixels})")
        await self.page.wait_for_timeout(300)

    async def scroll_to_bottom(self) -> None:
        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await self.page.wait_for_timeout(1000)

    async def hover(self, selector: str, timeout: int = 5000) -> bool:
        try:
            locator = self._resolve_locator(selector)
            await locator.first.hover(timeout=timeout)
            await self.page.wait_for_timeout(300)
            return True
        except Exception as e:
            logger.warning("Hover fallito su '%s': %s", selector, e)
            return False

    async def extract_text(self, selector: str) -> Optional[str]:
        try:
            locator = self._resolve_locator(selector)
            return await locator.first.inner_text()
        except Exception as e:
            logger.warning("Extract text fallito su '%s': %s", selector, e)
            return None

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    async def wait_for_navigation(self, timeout: int = 15000) -> bool:
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
            return True
        except Exception:
            return False

    def _resolve_locator(self, selector: str) -> Locator:
        if selector.startswith("//") or selector.startswith("("):
            return self.page.locator(f"xpath={selector}")
        if selector.startswith("text=") or selector.startswith("role="):
            return self.page.locator(selector)
        return self.page.locator(f"css={selector}")
