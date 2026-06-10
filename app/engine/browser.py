from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser

logger = logging.getLogger("scraper.engine")


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
        self._screenshot_dir = Path(".screenshots")
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def start(self, headless: bool = True) -> None:
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        logger.info("Browser avviato")

    async def new_page(
        self,
        user_agent: Optional[str] = None,
        viewport: dict[str, int] | None = None,
    ) -> Page:
        if self._browser is None:
            await self.start()
        context = await self._browser.new_context(
            user_agent=user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport=viewport or {"width": 1366, "height": 900},
            locale="it-IT",
            java_script_enabled=True,
            ignore_https_errors=False,
        )
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        """)
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
