from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from playwright.async_api import Page

from app.models.scrape_result import ScrapeResult


class BaseAdapter(ABC):
    name: str = "base"
    domain_patterns: list[str] = []

    async def before_navigate(self, page: Page, url: str) -> None:
        """Hook eseguito sulla pagina PRIMA del goto.

        Utile per agganciare listener di rete (es. catturare le risposte
        dell'API interna di un sito) che devono essere attivi durante il
        caricamento. Di default non fa nulla.
        """
        return None

    @abstractmethod
    async def scrape(self, page: Page, url: str, keywords: list[str] | None = None) -> ScrapeResult:
        ...

    @classmethod
    def matches(cls, url: str) -> bool:
        if not cls.domain_patterns:
            return False
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        return any(p in domain for p in cls.domain_patterns)
