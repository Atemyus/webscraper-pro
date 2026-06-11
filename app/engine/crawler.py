"""Crawler per "svuotare" interi siti di statistiche.

Due implementazioni:

* :class:`SoccerStatsCrawler` — crawl strutturato di SoccerStats (tutti i
  campionati × tutte le pagine-metrica) via HTTP diretto (veloce, il sito non è
  protetto).
* :class:`GenericSiteCrawler` — crawl generico in ampiezza (BFS) di qualsiasi
  sito (es. **fbref.com**, **footystats.org**): segue i link interni ed estrae
  tutte le tabelle dati di ogni pagina. Per i siti protetti da Cloudflare usa il
  browser reale riusando il cookie del challenge tra le pagine; gestisce inoltre
  le tabelle che fbref nasconde dentro i commenti HTML.

Tutte le tabelle vengono etichettate (sito, pagina/competizione) e aggregate in
un unico :class:`ScrapeResult` esportabile in CSV/JSON/Excel.
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
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment

from app.models.scrape_result import ScrapeResult, ScrapedItem

logger = logging.getLogger("scraper.crawler")

try:
    from curl_cffi import requests as _cffi_requests
    _HAS_CFFI = True
except Exception:  # pragma: no cover
    _HAS_CFFI = False

try:
    import cloudscraper as _cloudscraper
    _HAS_CLOUDSCRAPER = True
except Exception:  # pragma: no cover
    _HAS_CLOUDSCRAPER = False

import requests as _std_requests

ProgressCb = Callable[[int, int, str], Optional[Awaitable[None]]]

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

_CF_MARKERS = ("just a moment", "ci siamo quasi", "checking your browser",
               "verifica di sicurezza", "enable javascript and cookies",
               "verifying you are human", "attendere prego")

# Domini protetti da Cloudflare: vanno crawlati col browser (riuso del cookie).
_CF_DOMAINS = ("fbref.com", "footystats.org", "sofascore.com")


def _is_challenge(html: str) -> bool:
    low = (html or "")[:6000].lower()
    return any(m in low for m in _CF_MARKERS)


def _proxies() -> dict | None:
    raw = os.environ.get("SCRAPER_PROXY") or os.environ.get("HTTPS_PROXY")
    if not raw:
        return None
    if "://" not in raw:
        raw = f"http://{raw}"
    return {"http": raw, "https": raw}


# --------------------------------------------------------------------------- #
# Estrazione tabelle (con supporto alle tabelle nei commenti, vedi fbref)
# --------------------------------------------------------------------------- #
def _collect_tables(html: str):
    soup = BeautifulSoup(html, "lxml")
    tables = list(soup.find_all("table"))
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "<table" in c:
            try:
                tables.extend(BeautifulSoup(c, "lxml").find_all("table"))
            except Exception:
                pass
    return soup, tables


def _data_tables(tables, base_attrs: dict, max_tables: int) -> list[ScrapedItem]:
    candidates: list[tuple[int, list[list[str]], object]] = []
    for t in tables:
        if t.find("table"):
            continue  # tabella di layout
        rows: list[list[str]] = []
        for tr in t.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c != ""]
            if cells:
                rows.append(cells)
        if len(rows) < 4 or max(len(r) for r in rows) < 2:
            continue
        candidates.append((len(rows), rows, t))

    candidates.sort(key=lambda x: -x[0])
    items: list[ScrapedItem] = []
    for _, rows, t in candidates[:max_tables]:
        ncol = Counter(len(r) for r in rows).most_common(1)[0][0]
        rows = [r for r in rows if len(r) == ncol]
        if len(rows) < 4:
            continue
        headers, body = rows[0], rows[1:]
        attrs = dict(base_attrs)
        tid = t.get("id") or ""
        if tid:
            attrs["tabella"] = str(tid)[:50]
        attrs["rows"] = str(len(body))
        items.append(ScrapedItem(
            type="table",
            content={"headers": headers, "rows": body[:300]},
            selector=f"{base_attrs.get('source', 'site')}:table",
            attributes=attrs,
        ))
    return items


def _internal_links(html: str, base_url: str, domain: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    out: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        h = a["href"].split("#")[0].strip()
        if not h or h.startswith(("mailto:", "javascript:", "tel:")):
            continue
        full = urljoin(base_url, h).split("#")[0]
        p = urlparse(full)
        if p.scheme not in ("http", "https") or domain not in p.netloc.lower():
            continue
        if any(full.lower().endswith(ext) for ext in
               (".jpg", ".jpeg", ".png", ".gif", ".css", ".js", ".svg", ".pdf",
                ".zip", ".ico", ".woff", ".woff2", ".mp4", ".webp")):
            continue
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


# --------------------------------------------------------------------------- #
# Fetcher HTTP (rate limit + cache + cloudscraper/curl_cffi + proxy)
# --------------------------------------------------------------------------- #
class _HttpFetcher:
    def __init__(self, min_interval: float = 1.0):
        self.min_interval = min_interval
        self._last = 0.0
        self._cache: dict[str, str] = {}
        self._proxies = _proxies()
        self._scraper = None
        if _HAS_CLOUDSCRAPER:
            try:
                self._scraper = _cloudscraper.create_scraper(
                    browser={"browser": "chrome", "platform": "windows", "desktop": True})
            except Exception:
                self._scraper = None

    def get(self, url: str, retries: int = 2) -> str:
        if url in self._cache:
            return self._cache[url]
        elapsed = time.time() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed + random.uniform(0, 0.3))
        self._last = time.time()

        headers = {"User-Agent": _UA, "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"}
        for attempt in range(1, retries + 1):
            for fetch in self._backends():
                try:
                    html = fetch(url, headers)
                    if html and not _is_challenge(html):
                        self._cache[url] = html
                        return html
                except Exception as e:
                    logger.debug("fetch %s fallito: %s", url, e)
            time.sleep(1.5 * attempt)
        return ""

    def _backends(self):
        def cffi(url, headers):
            if not _HAS_CFFI:
                return ""
            r = _cffi_requests.get(url, impersonate="chrome", timeout=25,
                                   headers=headers, proxies=self._proxies)
            return r.text if r.status_code == 200 else ""

        def cloud(url, headers):
            if not self._scraper:
                return ""
            r = self._scraper.get(url, timeout=40, headers=headers, proxies=self._proxies)
            return r.text if r.status_code == 200 else ""

        def std(url, headers):
            r = _std_requests.get(url, timeout=25, headers=headers, proxies=self._proxies)
            return r.text if r.status_code == 200 else ""

        return [cffi, cloud, std]


# --------------------------------------------------------------------------- #
# SoccerStats: crawl strutturato (tutti i campionati × metriche)
# --------------------------------------------------------------------------- #
class SoccerStatsCrawler:
    BASE = "https://www.soccerstats.com"
    METRIC_PAGES: list[tuple[str, str]] = [
        ("latest.asp", "Classifica"), ("formtable.asp", "Form"),
        ("homeaway.asp", "Casa/Trasferta"), ("halftime.asp", "Primo tempo"),
        ("timing.asp", "Timing gol"), ("trends.asp", "Trends"),
        ("widetable.asp", "Tabella estesa"), ("scorers.asp", "Marcatori"),
        ("firstgoal.asp", "Primo gol"), ("table.asp", "Corner"),
    ]

    def __init__(self, min_interval: float = 1.0, max_tables_per_page: int = 6):
        self.max_tables_per_page = max_tables_per_page
        self.http = _HttpFetcher(min_interval)

    def discover_leagues(self) -> list[str]:
        html = self.http.get(self.BASE + "/")
        leagues, seen = [], set()
        for m in re.finditer(r"league=([a-zA-Z0-9_]+)", html):
            if m.group(1) not in seen:
                seen.add(m.group(1))
                leagues.append(m.group(1))
        return leagues

    async def crawl(self, leagues: Optional[list[str]] = None, max_leagues: int = 0,
                    progress_cb: Optional[ProgressCb] = None) -> ScrapeResult:
        if leagues is None:
            leagues = await asyncio.to_thread(self.discover_leagues)
        if max_leagues and max_leagues > 0:
            leagues = leagues[:max_leagues]

        result = ScrapeResult(url=self.BASE, title="SoccerStats — crawl completo")
        total = len(leagues) * len(self.METRIC_PAGES)
        done = 0
        dedup: set[str] = set()

        async def report(msg: str) -> None:
            if progress_cb:
                r = progress_cb(done, total, msg)
                if asyncio.iscoroutine(r):
                    await r

        for li, league in enumerate(leagues, 1):
            for asp, metrica in self.METRIC_PAGES:
                url = f"{self.BASE}/{asp}?league={league}"
                html = await asyncio.to_thread(self.http.get, url)
                done += 1
                if html:
                    _, tables = _collect_tables(html)
                    for item in _data_tables(tables, {"source": "soccerstats", "league": league,
                                                      "metrica": metrica}, self.max_tables_per_page):
                        key = f"{league}|{metrica}|{item.content['headers']}|{item.content['rows'][:1]}"
                        if key not in dedup:
                            dedup.add(key)
                            result.items.append(item)
                if done % 5 == 0 or asp == self.METRIC_PAGES[0][0]:
                    await report(f"Campionato {li}/{len(leagues)}: {league} — {metrica}")

        leghe = len({i.attributes.get("league") for i in result.items})
        result.title = f"SoccerStats — crawl: {leghe} campionati, {len(result.items)} tabelle"
        result.notice = (
            f"Crawl completo: {done} pagine, {len(leagues)} campionati, "
            f"{len(result.items)} tabelle dati. Usa 'Scarica tutto' per l'intero dataset.")
        await report("Completato")
        return result


# --------------------------------------------------------------------------- #
# Crawler generico (BFS) per qualsiasi sito — incl. fbref, footystats
# --------------------------------------------------------------------------- #
class GenericSiteCrawler:
    def __init__(self, start_url: str, max_pages: int = 150,
                 min_interval: float = 0.0, max_tables_per_page: int = 8,
                 path_prefix: str | None = None):
        if "://" not in start_url:
            start_url = "https://" + start_url
        self.start_url = start_url
        self.domain = urlparse(start_url).netloc.lower().replace("www.", "")
        self.max_pages = max(1, max_pages)
        self.max_tables_per_page = max_tables_per_page
        self.path_prefix = path_prefix
        self.use_browser = any(d in self.domain for d in _CF_DOMAINS)
        # fbref limita molto la frequenza: rallenta se non specificato.
        default_iv = 3.0 if self.use_browser else 1.0
        self.min_interval = min_interval or default_iv
        self.http = None if self.use_browser else _HttpFetcher(self.min_interval)

    def _label(self, url: str, soup: Optional[BeautifulSoup]) -> str:
        title = ""
        if soup is not None and soup.title and soup.title.string:
            title = soup.title.string.strip()[:60]
        path = urlparse(url).path or "/"
        return title or path

    def _ingest(self, html: str, url: str, result: ScrapeResult, dedup: set) -> None:
        soup, tables = _collect_tables(html)
        label = self._label(url, soup)
        for item in _data_tables(tables, {"source": self.domain, "pagina": label,
                                          "url": url}, self.max_tables_per_page):
            key = f"{label}|{item.content['headers']}|{item.content['rows'][:1]}"
            if key not in dedup:
                dedup.add(key)
                result.items.append(item)

    def _enqueue(self, html: str, url: str, queue: list, seen: set) -> None:
        for link in _internal_links(html, url, self.domain):
            if link in seen:
                continue
            if self.path_prefix and self.path_prefix not in urlparse(link).path:
                continue
            if len(seen) < self.max_pages * 5:
                seen.add(link)
                queue.append(link)

    async def crawl(self, progress_cb: Optional[ProgressCb] = None) -> ScrapeResult:
        result = ScrapeResult(url=self.start_url, title=f"{self.domain} — crawl")
        dedup: set[str] = set()
        queue: list[str] = [self.start_url]
        seen: set[str] = {self.start_url}
        done = 0

        async def report(msg: str) -> None:
            if progress_cb:
                r = progress_cb(done, self.max_pages, msg)
                if asyncio.iscoroutine(r):
                    await r

        if self.use_browser:
            from app.engine import BrowserManager
            bm = BrowserManager()
            await bm.start(headless=True)
            page = await bm.new_page()
            try:
                while queue and done < self.max_pages:
                    url = queue.pop(0)
                    html = await self._browser_get(page, url)
                    done += 1
                    if html:
                        self._ingest(html, url, result, dedup)
                        self._enqueue(html, url, queue, seen)
                    await report(f"Pagina {done}/{self.max_pages}: {urlparse(url).path[:50]}")
                    await page.wait_for_timeout(int(self.min_interval * 1000))
            finally:
                try:
                    await page.context.close()
                except Exception:
                    pass
        else:
            while queue and done < self.max_pages:
                url = queue.pop(0)
                html = await asyncio.to_thread(self.http.get, url)
                done += 1
                if html:
                    self._ingest(html, url, result, dedup)
                    self._enqueue(html, url, queue, seen)
                if done % 3 == 0 or done == 1:
                    await report(f"Pagina {done}/{self.max_pages}: {urlparse(url).path[:50]}")

        result.title = f"{self.domain} — crawl: {done} pagine, {len(result.items)} tabelle"
        if len(result.items) == 0 and self.use_browser:
            result.notice = (
                f"Nessun dato da {self.domain}: il sito è protetto da Cloudflare e il "
                "browser non ha superato la verifica da questo IP. Avvia l'app dal tuo PC "
                "(IP residenziale) o imposta un proxy nelle Impostazioni e riprova.")
        else:
            result.notice = (
                f"Crawl di {self.domain}: visitate {done} pagine, estratte "
                f"{len(result.items)} tabelle dati. Aumenta 'Max pagine' per andare più a "
                "fondo. Usa 'Scarica tutto' per l'intero dataset in CSV/JSON/Excel.")
        await report("Completato")
        return result

    async def _browser_get(self, page, url: str) -> str:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        except Exception as e:
            logger.debug("goto %s: %s", url, e)
            return ""
        # Attendi l'eventuale superamento del challenge Cloudflare (cookie riusato).
        for _ in range(12):
            try:
                html = await page.content()
            except Exception:
                return ""
            if not _is_challenge(html):
                return html
            await page.wait_for_timeout(2000)
        return ""


def is_soccerstats(url: str) -> bool:
    return "soccerstats" in urlparse(url if "://" in url else f"http://{url}").netloc.lower()
