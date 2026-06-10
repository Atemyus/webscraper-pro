from __future__ import annotations

from playwright.async_api import Page

from app.engine.extractor import ContentExtractor
from app.models.scrape_result import ScrapeResult
from .base_adapter import BaseAdapter


class GenericAdapter(BaseAdapter):
    name = "generic"
    domain_patterns = []

    def __init__(self):
        self.extractor = ContentExtractor()

    async def scrape(
        self, page: Page, url: str, keywords: list[str] | None = None
    ) -> ScrapeResult:
        html = await page.content()
        result = self.extractor.extract(html, url, keywords)
        return result
