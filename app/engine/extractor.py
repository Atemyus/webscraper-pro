from __future__ import annotations

import json
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

        # I dati strutturati (OpenGraph, meta, JSON-LD) sono presenti su quasi
        # ogni pagina — anche social e pagine dietro login — e contengono spesso
        # titolo, descrizione/caption, autore e immagine reali. Vanno per primi.
        all_items.extend(self._extract_structured(soup))
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

    # Etichette leggibili per i meta tag più utili.
    _META_HIGHLIGHTS = [
        ("og:title", "Titolo"),
        ("og:description", "Descrizione"),
        ("og:site_name", "Sito"),
        ("og:type", "Tipo contenuto"),
        ("og:image", "Immagine"),
        ("og:url", "URL"),
        ("article:author", "Autore"),
        ("article:published_time", "Pubblicato il"),
        ("twitter:title", "Titolo (Twitter/X)"),
        ("twitter:description", "Descrizione (Twitter/X)"),
        ("twitter:image", "Immagine (Twitter/X)"),
        ("description", "Meta description"),
        ("author", "Autore"),
        ("keywords", "Keywords"),
    ]

    def _extract_structured(self, soup: BeautifulSoup) -> list[ScrapedItem]:
        """Estrae OpenGraph, meta principali e dati strutturati JSON-LD.

        Sono i dati più affidabili: presenti su quasi ogni sito (social inclusi)
        anche quando il corpo della pagina è dietro un login.
        """
        items: list[ScrapedItem] = []
        seen: set[str] = set()
        meta = self._extract_metadata(soup)

        for key, label in self._META_HIGHLIGHTS:
            value = meta.get(key)
            if not value:
                continue
            content = f"{label}: {value}"
            if content in seen:
                continue
            seen.add(content)
            items.append(ScrapedItem(
                type="text",
                content=content,
                selector=f"meta[{key}]",
                attributes={"tag": "meta", "source": key},
            ))

        items.extend(self._extract_json_ld(soup, seen))
        return items

    def _extract_json_ld(self, soup: BeautifulSoup, seen: set[str]) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        fields = [
            ("name", "Nome"), ("headline", "Titolo"), ("alternativeHeadline", "Sottotitolo"),
            ("description", "Descrizione"), ("articleBody", "Contenuto"),
            ("datePublished", "Pubblicato il"), ("dateModified", "Aggiornato il"),
            ("uploadDate", "Caricato il"), ("price", "Prezzo"), ("priceCurrency", "Valuta"),
        ]

        for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = tag.string or tag.get_text() or ""
            raw = raw.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                continue

            objects = data if isinstance(data, list) else [data]
            # JSON-LD può annidare gli oggetti in @graph.
            flat: list[dict] = []
            for obj in objects:
                if isinstance(obj, dict):
                    graph = obj.get("@graph")
                    if isinstance(graph, list):
                        flat.extend(o for o in graph if isinstance(o, dict))
                    else:
                        flat.append(obj)

            for obj in flat:
                obj_type = obj.get("@type", "Dato")
                if isinstance(obj_type, list):
                    obj_type = ", ".join(str(t) for t in obj_type)
                parts: list[str] = []
                for key, label in fields:
                    val = obj.get(key)
                    if not val:
                        continue
                    val = self._flatten_jsonld_value(val)
                    if val:
                        parts.append(f"{label}: {val}")
                # Autore e rating sono spesso annidati.
                author = self._flatten_jsonld_value(obj.get("author"))
                if author:
                    parts.append(f"Autore: {author}")
                rating = obj.get("aggregateRating")
                if isinstance(rating, dict) and rating.get("ratingValue"):
                    rv = rating.get("ratingValue")
                    rc = rating.get("reviewCount") or rating.get("ratingCount")
                    parts.append(f"Valutazione: {rv}" + (f" ({rc} recensioni)" if rc else ""))

                if not parts:
                    continue
                content = f"[{obj_type}] " + " | ".join(parts)
                key = content[:120]
                if key in seen:
                    continue
                seen.add(key)
                items.append(ScrapedItem(
                    type="text",
                    content=content,
                    selector="script[ld+json]",
                    attributes={"tag": "json-ld", "schema": str(obj_type)},
                ))

        return items

    @staticmethod
    def _flatten_jsonld_value(val) -> str:
        if val is None:
            return ""
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, dict):
            return str(val.get("name") or val.get("@id") or val.get("url") or "").strip()
        if isinstance(val, list):
            flat = [ContentExtractor._flatten_jsonld_value(v) for v in val]
            return ", ".join(f for f in flat if f)
        return ""

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
