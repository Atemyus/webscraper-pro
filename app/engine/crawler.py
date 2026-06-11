"""Crawler completo di SoccerStats.

Visita TUTTI i campionati e, per ognuno, tutte le pagine-metrica principali
(classifica, form, casa/trasferta, timing gol, marcatori, ecc.), estraendo le
tabelle dati e aggregandole in un unico :class:`ScrapeResult`, con ogni tabella
etichettata per campionato e metrica.

Usa HTTP diretto (curl_cffi con impersonazione TLS di Chrome, fallback requests):
SoccerStats è server-rendered e non blocca queste richieste, quindi il crawl è
veloce e non richiede un browser per pagina. Rispetta un rate limit educato.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
from collections import Counter
from typing import Awaitable, Callable, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.models.scrape_result import ScrapeResult, ScrapedItem

logger = logging.getLogger("scraper.crawler")

try:
    from curl_cffi import requests as _cffi_requests
    _HAS_CFFI = True
except Exception:  # pragma: no cover
    _HAS_CFFI = False

import requests as _std_requests

ProgressCb = Callable[[int, int, str], Optional[Awaitable[None]]]


class SoccerStatsCrawler:
    BASE = "https://www.soccerstats.com"

    # Pagine-metrica per campionato (path .asp -> etichetta leggibile).
    METRIC_PAGES: list[tuple[str, str]] = [
        ("latest.asp", "Classifica"),
        ("formtable.asp", "Form"),
        ("homeaway.asp", "Casa/Trasferta"),
        ("halftime.asp", "Primo tempo"),
        ("timing.asp", "Timing gol"),
        ("trends.asp", "Trends"),
        ("widetable.asp", "Tabella estesa"),
        ("scorers.asp", "Marcatori"),
        ("firstgoal.asp", "Primo gol"),
        ("table.asp", "Corner"),
    ]

    _UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    def __init__(self, min_interval: float = 1.0, max_tables_per_page: int = 6):
        self.min_interval = min_interval
        self.max_tables_per_page = max_tables_per_page
        self._last = 0.0
        self._cache: dict[str, str] = {}
        proxy = os.environ.get("SCRAPER_PROXY") or os.environ.get("HTTPS_PROXY")
        self._proxies = ({"http": proxy, "https": proxy}
                         if proxy and "://" in proxy else
                         ({"http": f"http://{proxy}", "https": f"http://{proxy}"} if proxy else None))

    # ---- HTTP (sincrono, eseguito in thread) ----------------------------
    def _get(self, url: str, retries: int = 2) -> str:
        if url in self._cache:
            return self._cache[url]
        elapsed = time.time() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed + random.uniform(0, 0.3))
        self._last = time.time()

        headers = {"User-Agent": self._UA, "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"}
        for attempt in range(1, retries + 1):
            try:
                if _HAS_CFFI:
                    resp = _cffi_requests.get(url, impersonate="chrome", timeout=25,
                                              headers=headers, proxies=self._proxies)
                else:
                    resp = _std_requests.get(url, timeout=25, headers=headers, proxies=self._proxies)
                if resp.status_code == 200:
                    self._cache[url] = resp.text
                    return resp.text
                if resp.status_code == 429:
                    time.sleep(2 ** attempt * 2)
            except Exception as e:
                logger.debug("GET %s fallito (%s/%s): %s", url, attempt, retries, e)
                time.sleep(1.5 * attempt)
        return ""

    def discover_leagues(self) -> list[str]:
        html = self._get(self.BASE + "/")
        leagues: list[str] = []
        seen: set[str] = set()
        for m in re.finditer(r"league=([a-zA-Z0-9_]+)", html):
            code = m.group(1)
            if code not in seen:
                seen.add(code)
                leagues.append(code)
        return leagues

    # ---- estrazione tabelle dati ----------------------------------------
    def _extract_data_tables(self, html: str, league: str, metrica: str) -> list[ScrapedItem]:
        soup = BeautifulSoup(html, "lxml")
        candidates: list[tuple[int, list[list[str]]]] = []
        for t in soup.find_all("table"):
            if t.find("table"):
                continue  # tabella di layout (ne contiene altre)
            rows: list[list[str]] = []
            for tr in t.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                cells = [c for c in cells if c != ""]
                if cells:
                    rows.append(cells)
            if len(rows) < 4:
                continue
            if max(len(r) for r in rows) < 2:
                continue
            candidates.append((len(rows), rows))

        candidates.sort(key=lambda x: -x[0])
        items: list[ScrapedItem] = []
        for _, rows in candidates[: self.max_tables_per_page]:
            ncol = Counter(len(r) for r in rows).most_common(1)[0][0]
            rows = [r for r in rows if len(r) == ncol]
            if len(rows) < 4:
                continue
            headers, body = rows[0], rows[1:]
            items.append(ScrapedItem(
                type="table",
                content={"headers": headers, "rows": body[:200]},
                selector=f"soccerstats:{metrica}",
                attributes={"source": "soccerstats", "league": league,
                            "metrica": metrica, "rows": str(len(body))},
            ))
        return items

    # ---- crawl ----------------------------------------------------------
    async def crawl(
        self,
        leagues: Optional[list[str]] = None,
        max_leagues: int = 0,
        progress_cb: Optional[ProgressCb] = None,
    ) -> ScrapeResult:
        if leagues is None:
            leagues = await asyncio.to_thread(self.discover_leagues)
        if max_leagues and max_leagues > 0:
            leagues = leagues[:max_leagues]

        result = ScrapeResult(url=self.BASE, title="SoccerStats — crawl completo")
        total = len(leagues) * len(self.METRIC_PAGES)
        done = 0
        dedup: set[str] = set()

        async def report(msg: str) -> None:
            if progress_cb is None:
                return
            r = progress_cb(done, total, msg)
            if asyncio.iscoroutine(r):
                await r

        for li, league in enumerate(leagues, 1):
            for asp, metrica in self.METRIC_PAGES:
                url = f"{self.BASE}/{asp}?league={league}"
                html = await asyncio.to_thread(self._get, url)
                done += 1
                if html:
                    for item in self._extract_data_tables(html, league, metrica):
                        key = f"{league}|{metrica}|{item.content['headers']}|{item.content['rows'][:1]}"
                        if key in dedup:
                            continue
                        dedup.add(key)
                        result.items.append(item)
                # Aggiorna la GUI a inizio campionato e ogni 5 pagine.
                if done % 5 == 0 or asp == self.METRIC_PAGES[0][0]:
                    await report(f"Campionato {li}/{len(leagues)}: {league} — {metrica}")

        leghe = len({i.attributes.get("league") for i in result.items})
        result.title = f"SoccerStats — crawl: {leghe} campionati, {len(result.items)} tabelle"
        result.notice = (
            f"Crawl completo: visitate {done} pagine su {len(leagues)} campionati, "
            f"estratte {len(result.items)} tabelle dati (etichettate per campionato e metrica). "
            "Usa 'Scarica tutto' per avere l'intero dataset in CSV/JSON/Excel."
        )
        await report("Completato")
        return result


def is_soccerstats(url: str) -> bool:
    return "soccerstats" in urlparse(url if "://" in url else f"http://{url}").netloc.lower()
