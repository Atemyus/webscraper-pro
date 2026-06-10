"""
soccerstats.py
Scraping PURO di SoccerStats.com con BeautifulSoup (niente API, niente browser).
Le pagine sono tabelle HTML server-rendered: parsing diretto del DOM.

Il parser e' "header-driven": legge l'intestazione della tabella e mappa le
colonne per nome (GP, W, D, L, GF, GA, GD, Pts...). Cosi' resiste a piccoli
cambi nell'ordine delle colonne. Se il sito cambia struttura, basta ritoccare
il dizionario SYN qui sotto.

I 'league code' sono nel parametro ?league=... delle URL del sito
(es. italy, england, spain, germany, france...).
"""
from __future__ import annotations

import re

from base_scraper import BaseScraper
from models import TeamStanding


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip().replace("+", "")
    try:
        return int(value)
    except ValueError:
        m = re.search(r"-?\d+", value)
        return int(m.group()) if m else None


class SoccerStats(BaseScraper):
    BASE = "https://www.soccerstats.com"

    # sinonimi di intestazione -> nostro campo
    SYN: dict[str, set[str]] = {
        "position":       {"#", "pos", "rank", "no", "no."},
        "team":           {"team", "club"},
        "played":         {"gp", "pl", "mp", "played"},
        "won":            {"w"},
        "drawn":          {"d"},
        "lost":           {"l"},
        "goals_for":      {"gf"},
        "goals_against":  {"ga"},
        "goal_diff":      {"gd"},
        "points":         {"pts", "points"},
    }

    # ---- API pubblica dello scraper -------------------------------------
    def league_standings(self, league_code: str) -> list[TeamStanding]:
        """Classifica completa di un campionato (es. 'italy')."""
        html = self.get(f"{self.BASE}/latest.asp?league={league_code}")
        return self.parse_standings_html(html)

    # ---- parsing (separato dal fetch → testabile offline) ---------------
    def parse_standings_html(self, html: str) -> list[TeamStanding]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        table = self._find_standings_table(soup)
        if table is None:
            return []

        rows = table.find_all("tr")
        if not rows:
            return []

        headers = [c.get_text(strip=True).lower()
                   for c in rows[0].find_all(["th", "td"])]
        idx = self._column_index(headers)

        standings: list[TeamStanding] = []
        for i, tr in enumerate(rows[1:], start=1):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 5:
                continue
            texts = [c.get_text(strip=True) for c in cells]

            def col(key: str) -> str | None:
                j = idx.get(key)
                return texts[j] if (j is not None and j < len(texts)) else None

            team = col("team") or self._guess_team(cells, texts)
            if not team:
                continue

            standings.append(TeamStanding(
                position=_to_int(col("position")) or i,
                team=team,
                played=_to_int(col("played")),
                won=_to_int(col("won")),
                drawn=_to_int(col("drawn")),
                lost=_to_int(col("lost")),
                goals_for=_to_int(col("goals_for")),
                goals_against=_to_int(col("goals_against")),
                goal_diff=_to_int(col("goal_diff")),
                points=_to_int(col("points")),
            ))
        return standings

    # ---- helper interni --------------------------------------------------
    def _find_standings_table(self, soup):
        # SoccerStats usa storicamente <table id="btable"> per la classifica
        table = soup.find("table", id="btable")
        if table is not None:
            return table
        # fallback: la tabella piu' lunga che contiene 'team' e 'pts' nell'header
        best, best_rows = None, 0
        for tbl in soup.find_all("table"):
            head = tbl.get_text(" ", strip=True).lower()
            if "team" in head and ("pts" in head or "points" in head):
                n = len(tbl.find_all("tr"))
                if n > best_rows:
                    best, best_rows = tbl, n
        return best

    def _column_index(self, headers: list[str]) -> dict[str, int]:
        idx: dict[str, int] = {}
        for j, h in enumerate(headers):
            for key, syns in self.SYN.items():
                if h in syns and key not in idx:
                    idx[key] = j
        return idx

    @staticmethod
    def _guess_team(cells, texts) -> str | None:
        # la cella con un link <a> e' quasi sempre il nome squadra
        for c, t in zip(cells, texts):
            if c.find("a") and t:
                return t
        # altrimenti la cella di testo piu' lunga e non numerica
        candidates = [t for t in texts if t and not t.replace("+", "").lstrip("-").isdigit()]
        return max(candidates, key=len) if candidates else None
