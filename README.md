# WebScraper Pro

Un'applicazione professionale di web scraping con interfaccia grafica moderna (Flet). Inserisci un URL, specifica delle keywords, e ottieni tutte le informazioni rilevanti estratte automaticamente.

## Funzionalità

- **Scraping universale** — funziona con qualsiasi sito web
- **Filtro per keywords** — trova solo le informazioni che ti interessano
- **Estrazione intelligente** — testi, tabelle, link, immagini, metadati
- **Interazione con la pagina** — click, scroll, form filling, hover
- **Esportazione** — JSON, CSV, Excel con formattazione professionale
- **Browser headless** — basato su Playwright per gestire JS, SPA, Cloudflare
- **Interfaccia moderna** — tema scuro, design reattivo, tabs, statistiche in tempo reale

## Requisiti

- Python 3.10+
- [Playwright](https://playwright.dev/python/) (Chromium)

## Installazione

```bash
pip install -r requirements.txt
playwright install chromium
```

## Avvio

```bash
python main.py
```

## Struttura del progetto

```
app/
├── main.py                 # Entry point
├── gui/
│   ├── app.py              # App Flet principale (tema, navigazione)
│   ├── views/
│   │   ├── home_view.py    # Home: input URL, keywords, avvio scraping
│   │   └── results_view.py # Risultati: tabs, statistiche, esportazione
│   └── components/
│       └── result_card.py  # Card per elementi testo
├── engine/
│   ├── browser.py          # Gestione Playwright (headless browser)
│   ├── extractor.py        # Estrazione contenuti (HTML → dati strutturati)
│   ├── interactor.py       # Interazione con la pagina (click, scroll, etc.)
│   └── adapters/
│       ├── base_adapter.py    # Interfaccia adapter
│       └── generic_adapter.py # Adapter universale
├── models/
│   └── scrape_result.py    # Data models (ScrapeResult, ScrapedItem)
└── export/
    └── exporter.py         # Esportazione JSON / CSV / Excel
```

## Esempio d'uso

```python
from app.services import ScraperService
import asyncio

async def main():
    service = ScraperService()
    result = await service.scrape(
        url="https://example.com",
        keywords=["statistiche", "classifica"]
    )
    print(f"Trovati {len(result.items)} elementi")
    await service.export(result, "results", "json")
    await service.close()

asyncio.run(main())
```
