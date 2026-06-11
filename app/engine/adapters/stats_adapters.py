"""Adapter dedicati ai siti di statistiche calcistiche.

Strategie usate per estrarre dati COMPLETI nonostante le protezioni:

* **soccerstats.com / footystats.org** — server-rendered dietro Cloudflare. Si
  prova il browser headless (con attesa del challenge); se resta bloccato si
  ripiega su ``curl_cffi`` che imita il fingerprint TLS di Chrome (passa molti
  challenge passivi che il browser headless non supera), riusando i cookie già
  ottenuti dal browser.
* **sofascore.com** — single-page app: i dati arrivano via JavaScript dalla sua
  API interna ``api.sofascore.com``. Invece di scrapare il DOM offuscato,
  intercettiamo le risposte JSON che la pagina stessa riceve (event, statistiche,
  classifiche) e le trasformiamo in tabelle pulite.

Ogni adapter parte dall'estrazione generica (titolo, meta, OpenGraph, tutte le
tabelle, link, immagini) e vi **antepone** i dati strutturati specifici del sito.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.async_api import Page

from app.engine.extractor import ContentExtractor
from app.models.scrape_result import ScrapeResult, ScrapedItem
from .base_adapter import BaseAdapter

logger = logging.getLogger("scraper.adapters.stats")

try:
    from curl_cffi import requests as _cffi_requests
    _HAS_CFFI = True
except Exception:  # pragma: no cover
    _HAS_CFFI = False


_CLOUDFLARE_MARKERS = (
    "just a moment", "ci siamo quasi", "checking your browser", "cf-browser-verification",
    "challenge-platform", "verifying you are human", "needs to review the security",
    "enable javascript and cookies to continue", "verifica di sicurezza",
    "verifica riuscita", "controllo del browser", "attendere prego", "un attimo",
)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _is_challenge(title: str, html: str) -> bool:
    blob = (title + " " + (html or "")[:6000]).lower()
    return any(m in blob for m in _CLOUDFLARE_MARKERS)


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


async def _wait_through_cloudflare(page: Page, rounds: int = 16, pause_ms: int = 2000) -> bool:
    """Attende il superamento dell'eventuale challenge Cloudflare passivo."""
    for i in range(rounds):
        title, html = await _read(page)
        if not _is_challenge(title, html):
            return True
        await page.wait_for_timeout(pause_ms)
        if i == rounds // 2:
            try:
                await page.reload(wait_until="domcontentloaded", timeout=20000)
            except Exception:
                pass
    logger.warning("Challenge Cloudflare non superato dal browser")
    return False


async def _wait_for_any_table(page: Page, timeout: int = 12000) -> None:
    try:
        await page.wait_for_selector("table", timeout=timeout)
    except Exception:
        logger.debug("Nessuna <table> comparsa entro il timeout")


async def _curl_fetch_with_browser_cookies(page: Page, url: str) -> str | None:
    """Fallback HTTP con curl_cffi (TLS di Chrome), riusando i cookie del browser.

    Spesso supera i challenge Cloudflare passivi (basati su fingerprint TLS) che
    il browser headless non passa. Ritorna l'HTML o None se non utilizzabile."""
    if not _HAS_CFFI:
        return None
    try:
        ck = await page.context.cookies()
        jar = {c["name"]: c["value"] for c in ck if c.get("name")}
    except Exception:
        jar = {}

    for imp in ("chrome", "chrome124", "chrome120"):
        try:
            resp = _cffi_requests.get(
                url, impersonate=imp, cookies=jar or None, timeout=25,
                headers={"User-Agent": _UA, "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"},
            )
            if resp.status_code == 200 and not _is_challenge("", resp.text):
                logger.info("curl_cffi (%s) ha superato la protezione: %s", imp, url)
                return resp.text
        except Exception as e:
            logger.debug("curl_cffi %s fallito: %s", imp, e)
    return None


class _StatsBaseAdapter(BaseAdapter):
    """Browser + fallback curl_cffi, poi estrazione generica + dati in testa."""

    wait_for_table = True

    def __init__(self) -> None:
        self.extractor = ContentExtractor()

    async def scrape(self, page: Page, url: str, keywords: list[str] | None = None) -> ScrapeResult:
        if self.wait_for_table:
            await _wait_for_any_table(page)
        passed = await _wait_through_cloudflare(page)
        title, html = await _read(page)

        # Se il browser è ancora bloccato, tenta il fallback TLS con i suoi cookie.
        if not passed or _is_challenge(title, html):
            alt = await _curl_fetch_with_browser_cookies(page, url)
            if alt:
                html = alt

        result = self.extractor.extract(html, url, keywords)
        try:
            extra = self._extra_items(BeautifulSoup(html, "lxml"))
        except Exception as e:
            logger.debug("Estrazione dedicata fallita: %s", e)
            extra = []
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
    """Intercetta le risposte JSON dell'API interna di SofaScore.

    Le classi CSS del DOM sono offuscate, ma la pagina carica i dati da
    ``api.sofascore.com``: catturiamo quelle risposte e le rendiamo in tabelle."""

    name = "sofascore"
    domain_patterns = ["sofascore"]
    wait_for_table = False

    COMMON_LABELS = [
        "Ball possession", "Expected goals", "Total shots", "Shots on target",
        "Corner kicks", "Fouls", "Passes", "Yellow cards", "Possesso palla",
        "Tiri totali", "Tiri in porta", "Calci d'angolo", "Falli",
    ]

    def __init__(self) -> None:
        super().__init__()
        self._captured: list[tuple[str, dict]] = []

    async def before_navigate(self, page: Page, url: str) -> None:
        self._captured = []

        async def on_response(resp) -> None:
            try:
                if "api.sofascore.com" not in resp.url or resp.status != 200:
                    return
                ctype = (resp.headers or {}).get("content-type", "")
                if "json" not in ctype:
                    return
                data = await resp.json()
                if isinstance(data, dict):
                    self._captured.append((resp.url, data))
            except Exception:
                pass

        page.on("response", on_response)

    async def scrape(self, page: Page, url: str, keywords: list[str] | None = None) -> ScrapeResult:
        await _wait_through_cloudflare(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        # Dà tempo alle chiamate API (statistiche/standings) di completare.
        await page.wait_for_timeout(2500)

        html = await page.content()
        result = self.extractor.extract(html, url, keywords)

        api_items = self._items_from_api()
        if not api_items:
            # Fallback: parsing del testo renderizzato per etichetta.
            try:
                body_text = await page.inner_text("body")
            except Exception:
                body_text = ""
            stats = self._parse_stats_text(body_text)
            if stats:
                api_items = [stats]

        if api_items:
            result.items = api_items + result.items
        return result

    # ---- parsing dei payload dell'API -----------------------------------
    def _items_from_api(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        for u, data in self._captured:
            try:
                if u.endswith("/statistics") or "statistics" in data:
                    items += self._parse_statistics(data)
                elif "standings" in data:
                    items += self._parse_standings(data)
                elif "event" in data and isinstance(data["event"], dict):
                    summ = self._parse_event(data["event"])
                    if summ:
                        items.append(summ)
            except Exception as e:
                logger.debug("Parsing API sofascore fallito (%s): %s", u[:60], e)
        # dedup per contenuto
        seen, unique = set(), []
        for it in items:
            key = str(it.content)[:160]
            if key not in seen:
                seen.add(key)
                unique.append(it)
        return unique

    def _parse_statistics(self, data: dict) -> list[ScrapedItem]:
        out: list[ScrapedItem] = []
        for period in data.get("statistics", []):
            label = period.get("period", "ALL")
            rows: list[list[str]] = []
            for group in period.get("groups", []):
                for it in group.get("statisticsItems", []):
                    name = it.get("name", "")
                    home = str(it.get("home", it.get("homeValue", "")))
                    away = str(it.get("away", it.get("awayValue", "")))
                    if name:
                        rows.append([name, home, away])
            if rows:
                out.append(ScrapedItem(
                    type="table",
                    content={"headers": ["Statistica", "Casa", "Trasferta"], "rows": rows},
                    selector="sofascore:api:statistics",
                    attributes={"kind": "statistiche-partita", "periodo": str(label),
                                "rows": str(len(rows)), "source": "sofascore"},
                ))
        return out

    def _parse_standings(self, data: dict) -> list[ScrapedItem]:
        out: list[ScrapedItem] = []
        for table in data.get("standings", []):
            rows: list[list[str]] = []
            for row in table.get("rows", []):
                team = (row.get("team") or {}).get("name", "")
                if not team:
                    continue
                rows.append([
                    str(row.get("position", "")), team, str(row.get("matches", "")),
                    str(row.get("wins", "")), str(row.get("draws", "")), str(row.get("losses", "")),
                    str(row.get("scoresFor", "")), str(row.get("scoresAgainst", "")),
                    str(row.get("points", "")),
                ])
            if rows:
                out.append(ScrapedItem(
                    type="table",
                    content={"headers": ["Pos", "Squadra", "G", "V", "N", "P", "GF", "GS", "Punti"], "rows": rows},
                    selector="sofascore:api:standings",
                    attributes={"kind": "classifica", "rows": str(len(rows)), "source": "sofascore"},
                ))
        return out

    def _parse_event(self, ev: dict) -> ScrapedItem | None:
        home = (ev.get("homeTeam") or {}).get("name")
        away = (ev.get("awayTeam") or {}).get("name")
        if not home or not away:
            return None
        hs = (ev.get("homeScore") or {}).get("current", "")
        as_ = (ev.get("awayScore") or {}).get("current", "")
        tournament = (ev.get("tournament") or {}).get("name", "")
        status = (ev.get("status") or {}).get("description", "")
        content = f"{home} {hs} - {as_} {away}".strip()
        if tournament:
            content += f"  ({tournament})"
        if status:
            content += f" — {status}"
        return ScrapedItem(
            type="text",
            content=content,
            selector="sofascore:api:event",
            attributes={"tag": "match", "source": "sofascore"},
        )

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
