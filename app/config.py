"""Configurazione persistente dell'app (proxy, opzioni).

Salva su ``~/.webscraper_pro/config.json`` e applica i valori rilevanti come
variabili d'ambiente (es. SCRAPER_PROXY) lette dal motore di scraping.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("scraper.config")

_CONFIG_DIR = Path.home() / ".webscraper_pro"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


def load_config() -> dict:
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("Lettura config fallita: %s", e)
    return {}


def save_config(cfg: dict) -> None:
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("Salvataggio config fallito: %s", e)


def apply_config(cfg: dict | None = None) -> None:
    """Applica la configurazione all'ambiente (così il motore la usa)."""
    cfg = cfg if cfg is not None else load_config()
    proxy = (cfg.get("proxy") or "").strip()
    if proxy:
        os.environ["SCRAPER_PROXY"] = proxy
    else:
        os.environ.pop("SCRAPER_PROXY", None)


def get_proxy() -> str:
    return (load_config().get("proxy") or os.environ.get("SCRAPER_PROXY") or "").strip()


def set_proxy(value: str) -> None:
    cfg = load_config()
    cfg["proxy"] = (value or "").strip()
    save_config(cfg)
    apply_config(cfg)


def proxies_for_requests(proxy: str | None = None) -> dict | None:
    """Dict proxy nel formato requests/curl_cffi, o None."""
    proxy = (proxy if proxy is not None else get_proxy()).strip()
    if not proxy:
        return None
    if "://" not in proxy:
        proxy = f"http://{proxy}"
    return {"http": proxy, "https": proxy}


def check_exit_ip(proxy: str | None = None, timeout: int = 20) -> tuple[bool, str]:
    """Verifica l'IP di uscita (attraverso il proxy, se impostato).

    Ritorna (ok, messaggio). Utile per confermare che il proxy funziona."""
    proxies = proxies_for_requests(proxy)
    try:
        try:
            from curl_cffi import requests as _req
            kwargs = {"impersonate": "chrome"}
        except Exception:
            import requests as _req  # type: ignore
            kwargs = {}
        resp = _req.get("https://api.ipify.org?format=json", proxies=proxies,
                        timeout=timeout, **kwargs)
        ip = resp.json().get("ip", "?")
        via = " (via proxy)" if proxies else " (connessione diretta)"
        return True, f"IP di uscita: {ip}{via}"
    except Exception as e:
        return False, f"Verifica fallita: {str(e)[:120]}"
