"""Motore di applicazione dei filtri per categoria.

Questo modulo è ciò che fa *cozzare* i filtri scelti nella GUI con i dati
realmente estratti dalla pagina: prende un :class:`ScrapeResult` grezzo e i
filtri della categoria, e restituisce un risultato filtrato/ordinato.

Le euristiche (prezzi, voti, date, conteggi) sono volutamente *tolleranti*:
se un elemento non contiene un valore interpretabile per un dato filtro, non
viene scartato da quel filtro. Così i filtri "mordono" dove i dati lo
permettono senza svuotare i risultati su pagine generiche.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from app.models.scrape_result import ScrapeResult, ScrapedItem

logger = logging.getLogger("scraper.filters")


# Valori "select" che equivalgono a "nessun filtro".
_NEUTRAL_SELECT = {
    "", "tutto", "tutti", "tutte", "qualsiasi", "sempre",
    "rilevanza", "più rilevanti", "relevance", "any",
}

# Campi testo che restringono la ricerca a un contesto (oltre alle keywords).
_SCOPE_TEXT_FIELDS = (
    "account", "subreddit", "author", "brand", "source",
    "league", "team", "genre",
)

# Campi "select" che, se valorizzati e non neutri, fungono da termine extra.
_SCOPE_SELECT_FIELDS = ("category", "platform")

_CURRENCY_RE = re.compile(
    r"(?:€|\$|£|usd|eur|gbp)\s*([0-9][0-9.,]*)"
    r"|([0-9][0-9.,]*)\s*(?:€|\$|£|usd|eur|gbp|euro|dollari)",
    re.IGNORECASE,
)
_RATING_RE = re.compile(
    r"([0-5](?:[.,]\d)?)\s*(?:/\s*5|su\s*5|star|stelle|stars)",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"([0-9]{1,3})\s*(?:%|/\s*100|su\s*100)")
_INT_RE = re.compile(r"\d[\d.,]*")

_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), ("y", "m", "d")),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), ("d", "m", "y")),
    (re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b"), ("d", "m", "y")),
]

_PERIOD_DAYS = {
    "ultimo giorno": 1,
    "ultima settimana": 7,
    "ultimi 30 giorni": 30,
    "ultimo mese": 31,
    "ultimo anno": 365,
}


# --------------------------------------------------------------------------- #
# Helpers di parsing
# --------------------------------------------------------------------------- #
def _to_number(raw: str) -> Optional[float]:
    """Converte una stringa numerica (con separatori misti) in float."""
    raw = raw.strip()
    if not raw:
        return None
    # Normalizza separatori: rimuovi separatori migliaia, usa '.' per i decimali.
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        # virgola come decimale solo se seguita da 1-2 cifre finali
        if re.search(r",\d{1,2}$", raw):
            raw = raw.replace(",", ".")
        else:
            raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_int_filter(value: Any) -> Optional[float]:
    if value is None:
        return None
    num = _to_number(str(value))
    if num is None or num <= 0:
        return None
    return num


def _item_text(item: ScrapedItem) -> str:
    content = item.content
    if isinstance(content, dict):
        parts = [str(v) for v in content.values()]
    else:
        parts = [str(content)]
    if item.attributes:
        parts.extend(str(v) for v in item.attributes.values())
    return " ".join(parts)


def _extract_price(text: str) -> Optional[float]:
    best: Optional[float] = None
    for m in _CURRENCY_RE.finditer(text):
        num = _to_number(m.group(1) or m.group(2) or "")
        if num is not None and (best is None or num < best):
            best = num
    return best


def _extract_rating(text: str) -> Optional[float]:
    m = _RATING_RE.search(text)
    if m:
        return _to_number(m.group(1))
    return None


def _extract_percent(text: str) -> Optional[float]:
    m = _PERCENT_RE.search(text)
    if m:
        return _to_number(m.group(1))
    return None


def _extract_max_int(text: str) -> Optional[float]:
    nums = [
        _to_number(m.group(0))
        for m in _INT_RE.finditer(text)
    ]
    nums = [n for n in nums if n is not None]
    return max(nums) if nums else None


def _extract_date(text: str) -> Optional[datetime]:
    for pattern, order in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        parts = dict(zip(order, m.groups()))
        try:
            return datetime(int(parts["y"]), int(parts["m"]), int(parts["d"]))
        except (ValueError, KeyError):
            continue
    return None


def _split_terms(value: Any) -> list[str]:
    if not value:
        return []
    return [t.strip().lstrip("#@").lower() for t in str(value).replace(";", ",").split(",") if t.strip()]


def _select_value(filters: dict, key: str) -> Optional[str]:
    raw = filters.get(key)
    if raw is None:
        return None
    val = str(raw).strip()
    if val.lower() in _NEUTRAL_SELECT:
        return None
    return val


# --------------------------------------------------------------------------- #
# Engine principale
# --------------------------------------------------------------------------- #
def apply_category_filters(
    result: ScrapeResult,
    category: Optional[str],
    filters: Optional[dict],
    keywords: Optional[list[str]] = None,
) -> ScrapeResult:
    """Applica i filtri della categoria a ``result`` (in place) e lo ritorna."""
    if result.error or not result.items:
        return result

    filters = filters or {}
    items = list(result.items)
    original = len(items)

    # 1) Tipi di contenuto -------------------------------------------------- #
    items = _filter_content_types(items, filters)

    # 2) Keywords + termini di contesto (include / exclude) ----------------- #
    include_terms = list(keywords or [])
    include_terms += _split_terms(filters.get("keywords"))
    for field in _SCOPE_TEXT_FIELDS:
        include_terms += _split_terms(filters.get(field))
    for field in _SCOPE_SELECT_FIELDS:
        sv = _select_value(filters, field)
        if sv:
            include_terms += _split_terms(sv)
    include_terms = list(dict.fromkeys(t for t in include_terms if t))  # dedup

    exclude_terms = _split_terms(filters.get("exclude_keywords"))

    if include_terms:
        items = [it for it in items if _matches_any(it, include_terms)]
    if exclude_terms:
        items = [it for it in items if not _matches_any(it, exclude_terms)]

    # 3) Lunghezza minima del testo ---------------------------------------- #
    min_len = _parse_int_filter(filters.get("min_length"))
    if min_len:
        items = [
            it for it in items
            if it.type != "text" or len(str(it.content)) >= min_len
        ]

    # 4) Filtri numerici (prezzo, voto, conteggi) --------------------------- #
    items = _apply_numeric_filters(items, filters)

    # 5) Filtri sulle date / periodo --------------------------------------- #
    items = _apply_date_filters(items, filters)

    # 6) Ordinamento -------------------------------------------------------- #
    items = _sort_items(items, filters, include_terms)

    # 7) Limite massimo ----------------------------------------------------- #
    max_items = _parse_int_filter(filters.get("max_items"))
    if max_items:
        items = items[: int(max_items)]

    result.items = items
    logger.info(
        "Filtri categoria '%s': %d -> %d elementi", category or "general", original, len(items)
    )
    return result


def _matches_any(item: ScrapedItem, terms: list[str]) -> bool:
    text = _item_text(item).lower()
    return any(t in text for t in terms)


def _filter_content_types(items: list[ScrapedItem], filters: dict) -> list[ScrapedItem]:
    ct = _select_value(filters, "content_types")
    if ct:
        wanted = {
            "solo testi": "text",
            "solo tabelle": "table",
            "solo link": "link",
            "solo immagini": "image",
        }.get(ct.lower())
        if wanted:
            items = [it for it in items if it.type == wanted]

    if filters.get("include_images") is False:
        items = [it for it in items if it.type != "image"]
    if filters.get("include_links") is False:
        items = [it for it in items if it.type != "link"]
    return items


def _apply_numeric_filters(items: list[ScrapedItem], filters: dict) -> list[ScrapedItem]:
    price_min = _parse_int_filter(filters.get("price_min"))
    price_max = _parse_int_filter(filters.get("price_max"))
    min_reviews = _parse_int_filter(filters.get("min_reviews"))
    min_likes = _parse_int_filter(filters.get("min_likes"))
    min_comments = _parse_int_filter(filters.get("min_comments"))
    min_score = _parse_int_filter(filters.get("min_score"))
    min_value = _parse_int_filter(filters.get("min_value"))
    rating_pct = _parse_int_filter(filters.get("rating_min"))  # gaming 0-100
    min_stars = _stars_from_select(filters.get("min_rating"))

    # Soglia di conteggio unica (like / commenti / upvote / recensioni / valore).
    count_threshold = max(
        [v for v in (min_reviews, min_likes, min_comments, min_score, min_value) if v],
        default=None,
    )

    if not any([price_min, price_max, count_threshold, rating_pct, min_stars]):
        return items

    kept: list[ScrapedItem] = []
    for it in items:
        # Le tabelle e le immagini non passano per i filtri numerici testuali.
        if it.type in ("table", "image"):
            kept.append(it)
            continue

        text = _item_text(it)

        if price_min or price_max:
            price = _extract_price(text)
            if price is not None:
                if price_min and price < price_min:
                    continue
                if price_max and price > price_max:
                    continue

        if min_stars:
            stars = _extract_rating(text)
            if stars is not None and stars < min_stars:
                continue

        if rating_pct:
            pct = _extract_percent(text)
            if pct is not None and pct < rating_pct:
                continue

        if count_threshold:
            count = _extract_max_int(text)
            if count is not None and count < count_threshold:
                continue

        kept.append(it)
    return kept


def _apply_date_filters(items: list[ScrapedItem], filters: dict) -> list[ScrapedItem]:
    date_from = _parse_date_filter(filters.get("date_from"))
    date_to = _parse_date_filter(filters.get("date_to"))

    period = _select_value(filters, "time_period")
    if period and not date_from:
        days = _PERIOD_DAYS.get(period.lower())
        if days:
            date_from = datetime.now() - timedelta(days=days)

    if not date_from and not date_to:
        return items

    kept: list[ScrapedItem] = []
    for it in items:
        d = _extract_date(_item_text(it))
        if d is None:
            kept.append(it)  # nessuna data interpretabile: non scartare
            continue
        if date_from and d < date_from:
            continue
        if date_to and d > date_to:
            continue
        kept.append(it)
    return kept


def _sort_items(items: list[ScrapedItem], filters: dict, include_terms: list[str]) -> list[ScrapedItem]:
    sort_by = _select_value(filters, "sort_by")
    if not sort_by:
        # Default: rilevanza per keyword se presenti.
        if include_terms:
            items.sort(key=lambda it: _relevance(it, include_terms), reverse=True)
        return items

    sl = sort_by.lower()

    if "prezzo cresc" in sl or "price asc" in sl:
        items.sort(key=lambda it: _extract_price(_item_text(it)) or float("inf"))
    elif "prezzo decresc" in sl or "price desc" in sl:
        items.sort(key=lambda it: _extract_price(_item_text(it)) or float("-inf"), reverse=True)
    elif "valore cresc" in sl:
        items.sort(key=lambda it: _extract_max_int(_item_text(it)) or float("inf"))
    elif "valore decresc" in sl:
        items.sort(key=lambda it: _extract_max_int(_item_text(it)) or float("-inf"), reverse=True)
    elif "vecchi" in sl or "crescente" in sl:
        items.sort(key=lambda it: _extract_date(_item_text(it)) or datetime.max)
    elif any(k in sl for k in ("recent", "recenti", "new", "nuov")):
        items.sort(key=lambda it: _extract_date(_item_text(it)) or datetime.min, reverse=True)
    elif any(k in sl for k in ("popolari", "venduti", "utili", "top", "best", "hot", "rising", "recensioni", "divertenti")):
        items.sort(key=lambda it: _extract_max_int(_item_text(it)) or 0, reverse=True)
    elif include_terms:
        items.sort(key=lambda it: _relevance(it, include_terms), reverse=True)

    return items


def _relevance(item: ScrapedItem, terms: list[str]) -> int:
    text = _item_text(item).lower()
    return sum(text.count(t) for t in terms)


def _stars_from_select(value: Any) -> Optional[float]:
    if not value:
        return None
    m = re.search(r"([0-5])", str(value))
    return _to_number(m.group(1)) if m else None


def _parse_date_filter(value: Any) -> Optional[datetime]:
    if not value:
        return None
    return _extract_date(str(value))
