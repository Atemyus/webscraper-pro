"""Adapter dedicati ai siti di statistiche calcistiche.

Questi siti richiedono un trattamento speciale:

* **soccerstats.com** e **footystats.org**: pagine renderizzate lato server ma
  protette da Cloudflare. Il browser headless (con attesa del superamento del
  challenge) le rende correttamente quando il challenge è passivo.
* **sofascore.com**: è una single-page app, l'HTML statico è vuoto e i dati
  arrivano via JavaScript: serve un browser reale (Playwright) che esegua il JS.

Ogni adapter parte dall'estrazione generica (titolo, meta, OpenGraph, tutte le
tabelle, link, immagini) e vi **antepone** i dati strutturati specifici del sito
(classifica, riquadri statistici, statistiche partita), così lo scraping è
completo: dati puliti + tutto il resto della pagina.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from playwright.async_api import Page

from app.engine.extractor import ContentExtractor
from app.models.scrape_result import ScrapeResult, ScrapedItem
from .base_adapter import BaseAdapter

logger = logging.getLogger("scraper.adapters.stats")


_CLOUDFLARE_MARKERS = (
    # inglese
    "just a moment", "checking your browser", "cf-browser-verification",
    "challenge-platform", "verifying you are human", "needs to review the security",
    "enable javascript and cookies to continue",
    # italiano
    "verifica di sicurezza", "verifica riuscita", "controllo del browser",
    "attendere prego", "un attimo", "verifica che sei un essere umano",
    "consente di proteggersi dagli attacchi",
)


async def _read(page: Page) -> tuple[str, str]:
    try:
        title = (await page.title()) or ""
    except Exception:
        title = ""
    try:
        html = (await page.content()) or ""
    except Exception:
        html = ""
    return title, html


def _is_challenge(title: str, html: str) -> bool:
    blob = (title + " " + html[:6000]).lower()
    return any(m in blob for m in _CLOUDFLARE_MARKERS)


async def _wait_through_cloudflare(page: Page, rounds: int = 16, pause_ms: int = 2000) -> bool:
    """Attende il superamento dell'eventuale challenge Cloudflare.

    Ritorna True se la pagina sembra superata, False se è ancora bloccata
    (challenge interattivo che il browser headless non può risolvere)."""
    for i in range(rounds):
        title, html = await _read(page)
        if not _is_challenge(title, html):
            return True
        await page.wait_for_timeout(pause_ms)
        # A metà attesa un reload spesso sblocca i challenge passivi.
        if i == rounds // 2:
            try:
                await page.reload(wait_until="domcontentloaded", timeout=20000)
            except Exception:
                pass
    logger.warning("Challenge Cloudflare non superato (probabile verifica interattiva)")
    return False


async def _wait_for_any_table(page: Page, timeout: int = 12000) -> None:
    try:
        await page.wait_for_selector("table", timeout=timeout)
    except Exception:
        logger.debug("Nessuna <table> comparsa entro il timeout")


class _StatsBaseAdapter(BaseAdapter):
    """Logica comune: attesa Cloudflare + estrazione generica + dati in testa."""

    wait_for_table = True

    def __init__(self) -> None:
        self.extractor = ContentExtractor()

    async def scrape(self, page: Page, url: str, keywords: list[str] | None = None) -> ScrapeResult:
        if self.wait_for_table:
            await _wait_for_any_table(page)
        await _wait_through_cloudflare(page)
        html = await page.content()
        result = self.extractor.extract(html, url, keywords)
        soup = BeautifulSoup(html, "lxml")
        extra = self._extra_items(soup)
        if extra:
            result.items = extra + result.items
        return result

    def _extra_items(self, soup: BeautifulSoup) -> list[ScrapedItem]:
        return []


class SoccerStatsAdapter(_StatsBaseAdapter):
    name = "soccerstats"
    domain_patterns = ["soccerstats"]

    _POINTS_TOKENS = ("pts", "points", "punti")

    def _extra_items(self, soup: BeautifulSoup) -> list[ScrapedItem]:
        from collections import Counter

        table = self._find_standings_table(soup)
        if table is None:
            return []
        header = [c.get_text(strip=True) for c in table.find_all("tr")[0].find_all(["th", "td"])]
        data: list[list[str]] = []
        for tr in table.find_all("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c != ""]
            if cells:
                data.append(cells)
        if len(data) < 5:
            return []

        # Tieni solo le righe con il numero di colonne più frequente (scarta
        # titoli/sotto-intestazioni intrusi) e dai un'intestazione leggibile.
        ncol = Counter(len(r) for r in data).most_common(1)[0][0]
        data = [r for r in data if len(r) == ncol]
        if len([h for h in header if h]) != ncol:
            header = self._label_columns(ncol)

        return [ScrapedItem(
            type="table",
            content={"headers": header, "rows": data[:60]},
            selector="soccerstats:classifica",
            attributes={"kind": "classifica", "rows": str(len(data)), "source": "soccerstats"},
        )]

    @staticmethod
    def _label_columns(ncol: int) -> list[str]:
        presets = {
            2: ["Squadra", "Punti"],
            3: ["Squadra", "G", "Punti"],
            4: ["Squadra", "G", "DR", "Punti"],
            10: ["Pos", "Squadra", "G", "V", "N", "P", "GF", "GS", "DR", "Punti"],
        }
        return presets.get(ncol, [f"Col {i + 1}" for i in range(ncol)])

    def _find_standings_table(self, soup: BeautifulSoup):
        """Cerca la classifica: tabella con un header sui punti e un numero di
        righe compatibile con un campionato (evita le mega-tabelle contenitore)."""
        best, best_rows = None, 0
        for tbl in soup.find_all("table"):
            rows = tbl.find_all("tr")
            n = len(rows)
            if not (12 <= n <= 60):
                continue
            head = tbl.get_text(" ", strip=True)[:200].lower()
            if any(tok in head for tok in self._POINTS_TOKENS):
                if n > best_rows:
                    best, best_rows = tbl, n
        return best


class FootyStatsAdapter(_StatsBaseAdapter):
    name = "footystats"
    domain_patterns = ["footystats"]

    def _extra_items(self, soup: BeautifulSoup) -> list[ScrapedItem]:
        rows: list[list[str]] = []
        seen: set[str] = set()
        for el in soup.find_all(string=lambda s: s and "%" in s):
            value = el.strip()
            if not value or len(value) > 12 or "%" not in value:
                continue
            # L'etichetta può stare nel nodo stesso o in un antenato.
            label = ""
            node = el.parent
            for _ in range(3):
                if node is None:
                    break
                txt = node.get_text(" ", strip=True).replace(value, "").strip()
                if txt:
                    label = txt[:80]
                    break
                node = node.parent
            if not label:
                continue
            key = f"{label}|{value}"
            if key in seen:
                continue
            seen.add(key)
            rows.append([label, value])
        if not rows:
            return []
        return [ScrapedItem(
            type="table",
            content={"headers": ["Statistica", "Valore"], "rows": rows},
            selector="footystats:stat-boxes",
            attributes={"kind": "statistiche", "rows": str(len(rows)), "source": "footystats"},
        )]


class SofaScoreAdapter(_StatsBaseAdapter):
    name = "sofascore"
    domain_patterns = ["sofascore"]
    wait_for_table = False  # SPA: i dati raramente sono in <table>

    COMMON_LABELS = [
        "Ball possession", "Expected goals", "Total shots", "Shots on target",
        "Shots off target", "Blocked shots", "Corner kicks", "Fouls",
        "Passes", "Yellow cards", "Red cards", "Offsides", "Goalkeeper saves",
        "Big chances", "Tackles", "Possesso palla", "Tiri totali", "Tiri in porta",
        "Calci d'angolo", "Falli", "Passaggi", "Cartellini gialli",
    ]

    async def scrape(self, page: Page, url: str, keywords: list[str] | None = None) -> ScrapeResult:
        await _wait_through_cloudflare(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        try:
            body_text = await page.inner_text("body")
        except Exception:
            body_text = ""

        html = await page.content()
        result = self.extractor.extract(html, url, keywords)
        stats = self._parse_stats_text(body_text)
        if stats:
            result.items = [stats] + result.items
        return result

    def _parse_stats_text(self, text: str) -> ScrapedItem | None:
        if not text:
            return None
        rows: list[list[str]] = []
        seen: set[str] = set()
        for label in self.COMMON_LABELS:
            pattern = (re.escape(label)
                       + r"\D{0,15}?(\d+(?:[.,]\d+)?%?)\D{0,15}?(\d+(?:[.,]\d+)?%?)")
            m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if m and label.lower() not in seen:
                seen.add(label.lower())
                rows.append([label, m.group(1), m.group(2)])
        if not rows:
            return None
        return ScrapedItem(
            type="table",
            content={"headers": ["Statistica", "Casa", "Trasferta"], "rows": rows},
            selector="sofascore:match-stats",
            attributes={"kind": "statistiche-partita", "rows": str(len(rows)), "source": "sofascore"},
        )


STATS_ADAPTERS: list[BaseAdapter] = [
    SoccerStatsAdapter(),
    FootyStatsAdapter(),
    SofaScoreAdapter(),
]
