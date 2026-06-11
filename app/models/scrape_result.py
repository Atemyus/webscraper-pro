from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class ExportFormat(Enum):
    JSON = "json"
    CSV = "csv"
    EXCEL = "xlsx"


@dataclass
class ScrapedItem:
    type: str
    content: Any
    selector: Optional[str] = None
    attributes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScrapeResult:
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    metadata: dict[str, str] = field(default_factory=dict)
    items: list[ScrapedItem] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    error: Optional[str] = None
    notice: Optional[str] = None

    @property
    def texts(self) -> list[ScrapedItem]:
        return [i for i in self.items if i.type == "text"]

    @property
    def tables(self) -> list[ScrapedItem]:
        return [i for i in self.items if i.type == "table"]

    @property
    def links(self) -> list[ScrapedItem]:
        return [i for i in self.items if i.type == "link"]

    @property
    def images(self) -> list[ScrapedItem]:
        return [i for i in self.items if i.type == "image"]

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "metadata": self.metadata,
            "items": [i.to_dict() for i in self.items],
            "error": self.error,
            "notice": self.notice,
        }
