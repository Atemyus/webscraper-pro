"""
base_scraper.py
Fondamenta comuni a tutti gli scraper:
- sessione HTTP robusta (con curl_cffi per emulare il TLS di un browser reale → Cloudflare)
- rate limiting educato
- retry con backoff esponenziale
- cache su disco delle pagine
- helper get_soup() che restituisce direttamente una BeautifulSoup
"""
from __future__ import annotations

import time
import hashlib
import logging
import random
from pathlib import Path
from typing import Optional

import requests as _std_requests

try:
    from curl_cffi import requests as _cffi_requests
    _HAS_CFFI = True
except ImportError:
    _HAS_CFFI = False

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("scraper")


class RateLimiter:
    """Intervallo minimo (con jitter) fra una richiesta e la successiva."""

    def __init__(self, min_interval: float = 1.5):
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed + random.uniform(0, 0.4))
        self._last = time.time()


class BaseScraper:
    """Classe base: gli scraper dei singoli siti la estendono."""

    BASE: str = ""
    DEFAULT_HEADERS: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/webp,*/*;q=0.8"),
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    }

    def __init__(self, cache_dir: str = ".cache", min_interval: float = 1.5,
                 cache_ttl: int = 3600, impersonate: str | None = "chrome"):
        # curl_cffi emula il fingerprint TLS di Chrome → passa Cloudflare molto
        # piu' spesso di requests. Se non installato, ripiega su requests.
        if _HAS_CFFI and impersonate:
            self.session = _cffi_requests.Session(impersonate=impersonate)
        else:
            self.session = _std_requests.Session()
            if impersonate and not _HAS_CFFI:
                log.info("curl_cffi non installato: uso requests standard "
                         "(possibili 403 su siti protetti da Cloudflare)")

        self.session.headers.update(self.DEFAULT_HEADERS)
        self.limiter = RateLimiter(min_interval)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl

    # ---- cache su disco (HTML grezzo) ------------------------------------
    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha256(url.encode()).hexdigest()[:24]
        return self.cache_dir / f"{h}.html"

    def _read_cache(self, path: Path) -> Optional[str]:
        if path.exists() and (time.time() - path.stat().st_mtime) < self.cache_ttl:
            return path.read_text(encoding="utf-8")
        return None

    # ---- richiesta HTTP --------------------------------------------------
    def get(self, url: str, *, params: dict | None = None, retries: int = 3,
            use_cache: bool = True) -> str:
        """GET di una pagina HTML, con rate limit, retry, backoff e cache."""
        cache_path = self._cache_path(url) if (use_cache and params is None) else None
        if cache_path is not None:
            cached = self._read_cache(cache_path)
            if cached is not None:
                log.info("cache hit: %s", url)
                return cached

        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            self.limiter.wait()
            try:
                resp = self.session.get(url, params=params, timeout=25)
                if resp.status_code == 429:
                    wait = min(60, 2 ** attempt * 3)
                    log.warning("429 (rate limit), attendo %ss", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                html = resp.text
                if cache_path is not None:
                    cache_path.write_text(html, encoding="utf-8")
                return html
            except Exception as e:  # curl_cffi e requests sollevano tipi diversi
                last_err = e
                log.warning("tentativo %s/%s fallito: %s", attempt, retries, e)
                time.sleep(2 ** attempt)

        raise RuntimeError(f"Impossibile recuperare {url}: {last_err}")

    def get_soup(self, url: str, **kwargs):
        """Scarica una pagina e la restituisce gia' come BeautifulSoup."""
        from bs4 import BeautifulSoup
        return BeautifulSoup(self.get(url, **kwargs), "lxml")
