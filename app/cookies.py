"""Import dei cookie dal browser reale dell'utente (Chrome/Edge/Firefox...).

Permette di riusare la sessione che l'utente ha già sbloccato manualmente: se
apri footystats/fbref nel tuo browser e superi la verifica Cloudflare, qui
leggiamo il cookie ``cf_clearance`` e lo usiamo per lo scraping, evitando di
combattere di nuovo Turnstile.

Richiede ``browser_cookie3`` (opzionale). Funziona solo sulla macchina/utente
dove gira il browser.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("scraper.cookies")

# Ordine di tentativo dei browser supportati da browser_cookie3.
_BROWSERS = ("chrome", "edge", "brave", "chromium", "opera", "vivaldi", "firefox")


def _raw_cookies(domain: str) -> list:
    try:
        import browser_cookie3 as bc3
    except Exception:
        logger.debug("browser_cookie3 non installato")
        return []
    found: list = []
    for name in _BROWSERS:
        loader = getattr(bc3, name, None)
        if loader is None:
            continue
        try:
            for c in loader(domain_name=domain):
                found.append(c)
        except Exception as e:
            logger.debug("Lettura cookie da %s fallita: %s", name, e)
    return found


def load_cookies_dict(domain: str) -> dict:
    """Cookie del dominio come {nome: valore} (per requests/curl_cffi)."""
    return {c.name: c.value for c in _raw_cookies(domain) if c.value}


def load_cookies_for_playwright(domain: str) -> list[dict]:
    """Cookie nel formato accettato da context.add_cookies() di Playwright."""
    out: list[dict] = []
    for c in _raw_cookies(domain):
        if not c.value:
            continue
        out.append({
            "name": c.name,
            "value": c.value,
            "domain": c.domain or f".{domain}",
            "path": c.path or "/",
        })
    return out


def has_clearance(domain: str) -> bool:
    """True se nel browser dell'utente c'è un cf_clearance valido per il dominio."""
    return any(c.name == "cf_clearance" and c.value for c in _raw_cookies(domain))
