from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from app.models.scrape_result import ScrapeResult, ScrapedItem

logger = logging.getLogger("scraper.extractor")


class ContentExtractor:
    TAG_SCORES = {
        "h1": 100, "h2": 90, "h3": 80, "h4": 70, "h5": 60, "h6": 50,
        "title": 95, "p": 40, "article": 85, "section": 75,
    }

    def extract(self, html: str, url: str, keywords: list[str] | None = None) -> ScrapeResult:
        soup = BeautifulSoup(html, "lxml")
        result = ScrapeResult(url=url)

        result.title = self._extract_title(soup)
        result.description = self._extract_description(soup)
        result.metadata = self._extract_metadata(soup)

        all_items: list[ScrapedItem] = []

        all_items.extend(self._extract_text_blocks(soup, keywords))
        all_items.extend(self._extract_tables(soup, keywords))
        all_items.extend(self._extract_links(soup, keywords))
        all_items.extend(self._extract_images(soup, keywords))

        if keywords:
            all_items = self._filter_by_keywords(all_items, keywords)
            all_items.sort(key=lambda x: self._keyword_score(x, keywords), reverse=True)

        result.items = all_items
        return result

    def extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for tag in ("script", "style", "nav", "footer", "header", "aside"):
            for el in soup.find_all(tag):
                el.decompose()
        return soup.get_text(separator="\n", strip=True)

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        meta = soup.find("meta", attrs={"property": "og:description"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

    def _extract_metadata(self, soup: BeautifulSoup) -> dict[str, str]:
        meta: dict[str, str] = {}
        for tag in soup.find_all("meta"):
            name = tag.get("name") or tag.get("property") or ""
            content = tag.get("content", "")
            if name and content:
                meta[name.strip()] = content.strip()
        return meta

    def _extract_text_blocks(
        self, soup: BeautifulSoup, keywords: list[str] | None = None
    ) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        seen = set()

        for tag_name in ["h1", "h2", "h3", "h4", "h5", "h6", "p", "article", "section", "blockquote"]:
            for el in soup.find_all(tag_name):
                text = el.get_text(strip=True)
                if not text or len(text) < 10:
                    continue
                text_key = text[:100]
                if text_key in seen:
                    continue
                seen.add(text_key)
                items.append(ScrapedItem(
                    type="text",
                    content=text,
                    selector=self._make_selector(el),
                    attributes={"tag": tag_name, "length": str(len(text))},
                ))

        return items

    def _extract_tables(
        self, soup: BeautifulSoup, keywords: list[str] | None = None
    ) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        seen = set()

        for table in soup.find_all("table"):
            rows = []
            headers: list[str] = []

            thead = table.find("thead")
            if thead:
                headers = [c.get_text(strip=True) for c in thead.find_all(["th", "td"])]

            for tr in table.find_all("tr"):
                cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
                if cells:
                    rows.append(cells)

            if not rows:
                continue

            if not headers and rows:
                ths = table.find_all("th")
                if ths:
                    headers = [c.get_text(strip=True) for c in ths]

            table_key = str(rows[:3])
            if table_key in seen:
                continue
            seen.add(table_key)

            items.append(ScrapedItem(
                type="table",
                content={"headers": headers, "rows": rows},
                selector=self._make_selector(table),
                attributes={"rows": str(len(rows)), "cols": str(len(headers)) if headers else str(len(rows[0]))},
            ))

        return items

    def _extract_links(
        self, soup: BeautifulSoup, keywords: list[str] | None = None
    ) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        seen = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if not text or not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            link_key = f"{href}|{text}"
            if link_key in seen:
                continue
            seen.add(link_key)

            items.append(ScrapedItem(
                type="link",
                content={"url": href, "text": text},
                selector=self._make_selector(a),
                attributes={"href": href},
            ))

        return items

    def _extract_images(
        self, soup: BeautifulSoup, keywords: list[str] | None = None
    ) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        seen = set()

        for img in soup.find_all("img", src=True):
            src = img["src"]
            alt = img.get("alt", "")
            if not src or src.startswith("data:"):
                continue

            if src in seen:
                continue
            seen.add(src)

            items.append(ScrapedItem(
                type="image",
                content={"url": src, "alt": alt},
                selector=self._make_selector(img),
                attributes={"alt": alt, "width": img.get("width", ""), "height": img.get("height", "")},
            ))

        return items

    def _filter_by_keywords(
        self, items: list[ScrapedItem], keywords: list[str]
    ) -> list[ScrapedItem]:
        if not keywords:
            return items

        filtered: list[ScrapedItem] = []
        for item in items:
            if item.type == "text":
                text = str(item.content).lower()
                if any(k.lower() in text for k in keywords):
                    filtered.append(item)
            elif item.type == "table":
                content_str = str(item.content).lower()
                if any(k.lower() in content_str for k in keywords):
                    filtered.append(item)
            elif item.type == "link":
                content_str = (item.content.get("text", "") + " " + item.content.get("url", "")).lower()
                if any(k.lower() in content_str for k in keywords):
                    filtered.append(item)
            elif item.type == "image":
                alt = item.attributes.get("alt", "").lower()
                if any(k.lower() in alt for k in keywords):
                    filtered.append(item)
            else:
                filtered.append(item)

        return filtered

    def _keyword_score(self, item: ScrapedItem, keywords: list[str]) -> int:
        score = 0
        content_str = str(item.content).lower() if item.content else ""

        for k in keywords:
            kl = k.lower()
            count = content_str.count(kl)
            score += count * 10

        if item.type == "text":
            tag = item.attributes.get("tag", "")
            score += self.TAG_SCORES.get(tag, 0)

        if item.type == "table":
            score += 50

        return score

    def _make_selector(self, el: Tag) -> str:
        parts = []
        if el.get("id"):
            return f"#{el['id']}"
        for parent in el.parents:
            if parent.name == "body":
                break
            if parent.get("id"):
                parts.insert(0, f"#{parent['id']}")
                break
        tag = el.name
        classes = el.get("class", [])
        class_part = ".".join(classes) if classes else ""
        selector = f"{tag}.{class_part}" if class_part else tag
        if "." in selector:
            parts.append(selector)
        elif parts:
            parts.append(selector)
        else:
            parts.append(selector)

        return " > ".join(parts) if parts else tag or "unknown"
