from __future__ import annotations

import flet as ft
from typing import Any


class FilterDef:
    def __init__(
        self,
        key: str,
        label: str,
        filter_type: str = "text",
        hint: str = "",
        options: list[str] | None = None,
        default: Any = None,
        expandable: bool = False,
    ):
        self.key = key
        self.label = label
        self.filter_type = filter_type
        self.hint = hint
        self.options = options or []
        self.default = default
        self.expandable = expandable


class CategoryDef:
    def __init__(
        self,
        key: str,
        label: str,
        icon: str,
        description: str,
        color: str,
        filters: list[FilterDef],
        domain_patterns: list[str] | None = None,
    ):
        self.key = key
        self.label = label
        self.icon = icon
        self.description = description
        self.color = color
        self.filters = filters
        self.domain_patterns = domain_patterns or []

    def matches(self, url: str) -> bool:
        if not self.domain_patterns:
            return False
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        return any(p in domain for p in self.domain_patterns)


GENERAL = CategoryDef(
    key="general",
    label="General",
    icon=ft.Icons.LANGUAGE,
    color=ft.Colors.INDIGO_400,
    description="Scraping generico per qualsiasi sito web. Estrai testo, tabelle, link e immagini.",
    filters=[
        FilterDef("keywords", "Keywords", "text", "es. prezzo, recensioni, specifiche"),
        FilterDef("wait_for", "Attendi selettore", "text", "es. .content, #main, .table-class"),
        FilterDef("max_items", "Max risultati", "number", "es. 50, 100, 0 = illimitato", default="0"),
        FilterDef("include_images", "Includi immagini", "checkbox", default=True),
        FilterDef("include_links", "Includi link", "checkbox", default=True),
    ],
    domain_patterns=[],
)

SOCIAL = CategoryDef(
    key="social",
    label="Social",
    icon=ft.Icons.SHARE,
    color=ft.Colors.PINK_400,
    description="Instagram, Facebook, Twitter/X, TikTok, LinkedIn. Estrai post, profili, hashtag.",
    filters=[
        FilterDef("keywords", "Keywords / Hashtag", "text", "es. #python, @user, tecnologia"),
        FilterDef("post_type", "Tipo contenuto", "select", options=["Tutti", "Post", "Reels/Video", "Storie", "Immagini"]),
        FilterDef("time_period", "Periodo", "select", options=["Ultimo giorno", "Ultima settimana", "Ultimo mese", "Ultimo anno", "Sempre"]),
        FilterDef("sort_by", "Ordina per", "select", options=["Più recenti", "Più popolari", "Più rilevanti"]),
        FilterDef("max_items", "Max risultati", "number", "es. 50", default="30"),
    ],
    domain_patterns=["instagram", "facebook", "twitter", "x.com", "tiktok", "linkedin"],
)

FORUMS = CategoryDef(
    key="forums",
    label="Forum",
    icon=ft.Icons.FORUM,
    color=ft.Colors.AMBER_400,
    description="Reddit, Quora, Stack Overflow, e community forum. Estrai discussioni, commenti, voti.",
    filters=[
        FilterDef("keywords", "Keywords", "text", "es. python, machine learning, gaming"),
        FilterDef("subreddit", "Community / Subreddit", "text", "es. python, italy, gaming"),
        FilterDef("time_period", "Periodo", "select", options=["Ultimo giorno", "Ultima settimana", "Ultimo mese", "Ultimo anno", "Sempre"]),
        FilterDef("sort_by", "Ordina per", "select", options=["Hot", "New", "Top", "Rising", "Best"]),
        FilterDef("max_items", "Max risultati", "number", "es. 50", default="50"),
    ],
    domain_patterns=["reddit", "quora", "stackoverflow", "stackexchange", "forum"],
)

GAMING = CategoryDef(
    key="gaming",
    label="Gaming",
    icon=ft.Icons.SPORTS_ESPORTS,
    color=ft.Colors.GREEN_400,
    description="Steam, Epic Games, Godot, Unity, giochi. Estrai recensioni, valutazioni, news.",
    filters=[
        FilterDef("keywords", "Keywords / Gioco", "text", "es. The Witcher, Elden Ring, Godot"),
        FilterDef("review_type", "Tipo recensioni", "select", options=["Tutte", "Positive", "Negative", "Recenti"]),
        FilterDef("rating_min", "Valutazione minima", "number", "es. 70", default="0"),
        FilterDef("sort_by", "Ordina per", "select", options=["Più utili", "Più recenti", "Più divertenti"]),
        FilterDef("time_period", "Periodo", "select", options=["Tutto", "Ultimi 30 giorni", "Ultimo anno"]),
        FilterDef("max_items", "Max risultati", "number", "es. 50", default="50"),
    ],
    domain_patterns=["steam", "epicgames", "gog", "godot", "unity", "itch.io", "metacritic", "opencritic"],
)

STATISTICS = CategoryDef(
    key="statistics",
    label="Statistiche",
    icon=ft.Icons.BAR_CHART,
    color=ft.Colors.CYAN_400,
    description="Siti di statistiche sportive, finanziarie, dati. Estrai tabelle, classifiche, metriche.",
    filters=[
        FilterDef("keywords", "Keywords", "text", "es. classifica, gol, punti, Serie A"),
        FilterDef("league", "Campionato / Lega", "text", "es. Serie A, Premier League, NBA"),
        FilterDef("season", "Stagione", "select", options=["Corrente", "2024/25", "2023/24", "2022/23", "2021/22"]),
        FilterDef("stat_type", "Tipo statistiche", "select", options=["Tutte", "Classifica", "Partite", "Giocatori", "Squadre"]),
        FilterDef("date_from", "Data inizio", "date", "es. 2024-01-01"),
        FilterDef("date_to", "Data fine", "date", "es. 2024-12-31"),
    ],
    domain_patterns=["soccerstats", "footystats", "sofascore", "transfermarkt", "flashscore", "espn", "bleacher"],
)

ECOMMERCE = CategoryDef(
    key="ecommerce",
    label="E-commerce",
    icon=ft.Icons.SHOPPING_CART,
    color=ft.Colors.ORANGE_400,
    description="Amazon, eBay, AliExpress, Etsy. Estrai prodotti, prezzi, recensioni, specifiche.",
    filters=[
        FilterDef("keywords", "Prodotto / Ricerca", "text", "es. iPhone 16, laptop gaming, scarpe"),
        FilterDef("price_min", "Prezzo minimo", "number", "es. 10"),
        FilterDef("price_max", "Prezzo massimo", "number", "es. 1000"),
        FilterDef("sort_by", "Ordina per", "select", options=["Più venduti", "Prezzo crescente", "Prezzo decrescente", "Migliori recensioni", "Più recenti"]),
        FilterDef("min_rating", "Valutazione minima", "select", options=["Qualsiasi", "3+ stelle", "4+ stelle", "5 stelle"]),
        FilterDef("min_reviews", "Minimo recensioni", "number", "es. 50", default="0"),
        FilterDef("max_items", "Max risultati", "number", "default: 50", default="50"),
    ],
    domain_patterns=["amazon", "ebay", "aliexpress", "etsy", "walmart", "bestbuy"],
)

NEWS = CategoryDef(
    key="news",
    label="Notizie",
    icon=ft.Icons.ARTICLE,
    color=ft.Colors.RED_400,
    description="Siti di news, blog, articoli. Estrai articoli, autori, date, contenuti.",
    filters=[
        FilterDef("keywords", "Keywords / Argomento", "text", "es. politica, tecnologia, sport"),
        FilterDef("source", "Fonte / Sito", "text", "es. repubblica, corriere, ansa"),
        FilterDef("date_from", "Data inizio", "date", "es. 2024-06-01"),
        FilterDef("date_to", "Data fine", "date", "es. 2024-12-31"),
        FilterDef("category", "Categoria", "select", options=["Tutte", "Politica", "Economia", "Tecnologia", "Sport", "Cultura", "Spettacolo"]),
        FilterDef("max_items", "Max articoli", "number", "default: 30", default="30"),
    ],
    domain_patterns=["ansa", "repubblica", "corriere", "lastampa", "tgcom", "wired", "techcrunch", "theverge"],
)

ALL_CATEGORIES: list[CategoryDef] = [
    GENERAL, SOCIAL, FORUMS, GAMING, STATISTICS, ECOMMERCE, NEWS,
]

CATEGORY_MAP: dict[str, CategoryDef] = {c.key: c for c in ALL_CATEGORIES}


def detect_category(url: str) -> str | None:
    """Auto-detect category from URL, returns category key or None."""
    for cat in ALL_CATEGORIES:
        if cat.matches(url):
            return cat.key
    return None


def get_category(key: str) -> CategoryDef:
    return CATEGORY_MAP.get(key, GENERAL)
