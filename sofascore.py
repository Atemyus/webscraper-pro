"""
sofascore.py
SofaScore e' una single-page app: l'HTML statico e' vuoto, i dati arrivano via
JavaScript. Quindi NON si scrapa con requests/BeautifulSoup. L'unico modo per
"leggere la pagina" senza usare la loro API e' un BROWSER HEADLESS che renderizza
il JS; poi si estrae dal testo/DOM gia' renderizzato.

Usa Playwright:
    pip install playwright
    playwright install chromium

Nota onesta: le classi CSS di SofaScore sono generate automaticamente (illeggibili),
quindi qui estraiamo per ETICHETTA VISIBILE (es. "Ball possession") leggendo il
testo renderizzato. E' robusto ai cambi di classe ma va tarato sul layout reale:
usa render_text() per vedere cosa arriva e adattare il parsing.
"""
from __future__ import annotations

import re

from base_scraper import BaseScraper
from models import StatRow


class SofaScore(BaseScraper):
    BASE = "https://www.sofascore.com"

    # etichette statistiche tipiche di una pagina partita
    COMMON_LABELS = [
        "Ball possession", "Expected goals", "Total shots", "Shots on target",
        "Shots off target", "Blocked shots", "Corner kicks", "Fouls",
        "Passes", "Yellow cards", "Red cards", "Offsides", "Goalkeeper saves",
        "Big chances", "Tackles",
    ]

    # ---- rendering con browser headless ---------------------------------
    def _render(self, url: str, wait_text: str | None = None,
                timeout: int = 35000) -> tuple[str, str]:
        """Apre la pagina in Chromium headless e ritorna (html, testo_visibile)."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=self.DEFAULT_HEADERS["User-Agent"],
                locale="it-IT",
                viewport={"width": 1366, "height": 900},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout)
            if wait_text:
                try:
                    page.get_by_text(wait_text, exact=False).first.wait_for(timeout=timeout)
                except Exception:
                    pass  # la pagina potrebbe non avere quella label: proseguiamo
            html = page.content()
            body_text = page.inner_text("body")
            browser.close()
        return html, body_text

    def render_text(self, url: str) -> str:
        """Testo visibile della pagina renderizzata (utile per capire il layout)."""
        return self._render(url)[1]

    def render_html(self, url: str) -> str:
        """HTML dopo l'esecuzione del JavaScript."""
        return self._render(url)[0]

    # ---- estrazione statistiche partita ---------------------------------
    def match_statistics(self, match_url: str) -> list[StatRow]:
        """
        Renderizza la pagina di una partita e prova a estrarre le statistiche
        per etichetta. 'match_url' e' l'URL completo della partita su sofascore.com.
        """
        _, text = self._render(match_url, wait_text="Ball possession")
        return self.parse_stats_text(text)

    def parse_stats_text(self, text: str) -> list[StatRow]:
        """
        Cerca, per ogni etichetta nota, due valori numerici (casa/trasferta)
        nelle vicinanze. Best-effort: se il layout reale e' diverso, adatta la regex.
        """
        rows: list[StatRow] = []
        for label in self.COMMON_LABELS:
            # ...label... num ... num   (numeri o percentuali, anche xG con decimali)
            pattern = (re.escape(label)
                       + r"\D{0,15}?(\d+(?:\.\d+)?%?)\D{0,15}?(\d+(?:\.\d+)?%?)")
            m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if m:
                rows.append(StatRow(label=label, home=m.group(1), away=m.group(2)))
        return rows
