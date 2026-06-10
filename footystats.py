"""
footystats.py
Scraping PURO del SITO footystats.org con BeautifulSoup (niente API ufficiale).

Le pagine di FootyStats sono renderizzate lato server ma complesse e dietro
Cloudflare: tieni curl_cffi installato (vedi base_scraper) per evitare i 403.

Poiche' la struttura DOM di FootyStats e' fitta e cambia spesso, qui l'approccio
e' GENERICO e robusto: estrai TUTTE le tabelle della pagina mappando le righe
sui rispettivi header. Poi scegli tu la tabella che ti interessa. I 'path' sono
quelli che vedi nell'URL del browser (es. 'italy/serie-a', 'england/premier-league').
"""
from __future__ import annotations

from base_scraper import BaseScraper


class FootyStats(BaseScraper):
    BASE = "https://footystats.org"

    def page(self, path: str):
        """Restituisce la pagina come BeautifulSoup."""
        return self.get_soup(f"{self.BASE}/{path.lstrip('/')}")

    def all_tables(self, path: str) -> list[list[dict]]:
        """
        Estrae OGNI tabella della pagina come lista di dizionari
        (una riga = un dict header->valore). Ritorna una lista di tabelle.
        """
        soup = self.page(path)
        tables: list[list[dict]] = []
        for tbl in soup.find_all("table"):
            rows = tbl.find_all("tr")
            if not rows:
                continue
            headers = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
            parsed: list[dict] = []
            for tr in rows[1:]:
                cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
                if not cells:
                    continue
                if headers and len(headers) == len(cells):
                    parsed.append(dict(zip(headers, cells)))
                else:
                    parsed.append({f"col{i}": v for i, v in enumerate(cells)})
            if parsed:
                tables.append(parsed)
        return tables

    def biggest_table(self, path: str) -> list[dict]:
        """Scorciatoia: la tabella con piu' righe (di solito la classifica)."""
        tables = self.all_tables(path)
        return max(tables, key=len) if tables else []

    def stat_boxes(self, path: str) -> list[dict]:
        """
        Estrae i 'riquadri statistici' (es. percentuali Over/Under, BTTS...).
        FootyStats li rende come blocchi con una percentuale ben visibile;
        qui prendiamo elementi con simbolo % e l'etichetta vicina.
        Da rifinire sulla pagina reale: stampa l'output e adatta i selettori.
        """
        soup = self.page(path)
        boxes: list[dict] = []
        for el in soup.find_all(string=lambda s: s and "%" in s):
            text = el.strip()
            if not text or len(text) > 12:
                continue
            parent = el.parent
            label = parent.get_text(" ", strip=True).replace(text, "").strip() if parent else ""
            boxes.append({"value": text, "label": label[:80]})
        return boxes
