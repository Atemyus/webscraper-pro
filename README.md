# WebScraper Pro

Un'applicazione professionale di web scraping con interfaccia grafica moderna (Flet). Inserisci un URL, specifica delle keywords, e ottieni tutte le informazioni rilevanti estratte automaticamente.

## Funzionalità

- **Scraping universale** — funziona con qualsiasi sito web
- **Categorie con filtri dedicati** — General, Social, Forum, Gaming, Statistiche, E-commerce, Notizie: ogni categoria ha i propri filtri pertinenti (prezzo, voto, periodo, brand, fonte, ecc.)
- **Filtri che "cozzano" davvero** — keywords, esclusioni, range di prezzo/voto/recensioni, intervalli di date, ordinamento e limite vengono applicati ai dati estratti (vedi `app/filters.py`)
- **Estrazione intelligente** — testi, tabelle, link, immagini, metadati
- **Interazione con la pagina** — click, scroll, form filling, hover
- **Esportazione** — JSON, CSV, Excel con formattazione professionale
- **Browser headless** — basato su Playwright per gestire JS, SPA, Cloudflare
- **Interfaccia moderna** — tema scuro, design reattivo, tabs, statistiche in tempo reale

## Filtri per categoria

Ogni categoria espone un set di filtri specifici. Esempi:

- **E-commerce**: brand, prezzo min/max, valutazione minima, n. recensioni, disponibilità, ordinamento
- **Notizie**: fonte, autore, categoria, intervallo di date, ordinamento (più recenti/vecchi)
- **Statistiche**: lega, squadra, stagione, tipo statistica, valore minimo, intervallo di date.
  Include l'opzione **"Scarica TUTTO il sito — crawl completo"**: svuota l'intero sito aggregando
  tutte le tabelle dati (etichettate per pagina/campionato), esportabili in CSV/JSON/Excel.
  Usa "Max campionati/pagine" per limitarne l'ampiezza. Due motori automatici:
  - **soccerstats** — crawl strutturato (tutti i campionati × tutte le pagine-metrica), via HTTP veloce.
  - **fbref, footystats e altri** — crawl generico in ampiezza (segue i link interni); per i siti
    protetti da Cloudflare usa il browser riusando il cookie del challenge e legge anche le tabelle
    nascoste nei commenti HTML (tipico di fbref). Per questi siti, da IP datacenter Cloudflare blocca:
    avvia l'app dal tuo PC o imposta un proxy in Impostazioni.
- **Social / Forum**: account/subreddit, autore, periodo, like/upvote/commenti minimi
- **Gaming**: genere, piattaforma, tipo recensioni, voto minimo, prezzo massimo

I filtri vengono applicati dopo l'estrazione da `apply_category_filters()` (`app/filters.py`) in
modo tollerante: un elemento privo di un valore interpretabile (es. nessun prezzo nel testo) non
viene scartato da quel filtro, così i filtri restringono i risultati senza svuotarli su pagine generiche.

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

## Siti protetti (Cloudflare) e proxy

Alcuni siti (es. **footystats.org**, **sofascore.com**) usano protezioni anti-bot
Cloudflare. L'app prova in cascata: Chrome reale + stealth → cloudscraper →
impersonazione TLS (curl_cffi), riusando i cookie del browser.

Quando il blocco dipende dall'**IP** (tipico di IP datacenter/VPS), nessuna
tecnica lato client basta: serve cambiare l'IP di uscita con un **proxy**
(preferibilmente residenziale). Impostalo con una variabile d'ambiente:

```bash
export SCRAPER_PROXY="http://utente:password@host:porta"
python main.py
```

Il proxy viene usato sia dal browser sia dai fallback HTTP. Per **soccerstats.com**
(non bloccato) non serve nulla.

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
