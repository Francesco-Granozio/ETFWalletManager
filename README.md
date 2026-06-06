# PAC ETF Tracker

Desktop app per tracciare un PAC ETF con:

- ripartizione attuale vs target;
- suggerimenti di acquisto per il prossimo PAC;
- snapshot fixed a inizio mese per performance mensile, YTD e anno su anno;
- cache SQLite locale dei prezzi con fallback manuale;
- provider opzionale `justetf-scraping` per quotazioni live Gettex/EUR.

## Avvio

```powershell
uv sync
uv run python main.py
```

Il database locale viene creato in `data/portfolio.db` vuoto, con sole impostazioni di base. Il censimento del PAC avviene manualmente dalla pagina `Simula ripartizione`, usando justETF per risolvere e mettere in cache i dati degli ISIN inseriti.

La pagina `Simula ripartizione` mantiene piu simulazioni salvate in una griglia espandibile. Una simulazione puo essere caricata, modificata, salvata come nuova simulazione o applicata come PAC attivo.

## Test

```powershell
uv run pytest
```
