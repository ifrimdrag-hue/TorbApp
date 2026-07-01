# Forecast module

Localizare: `app/forecast/` + pagina `/forecast` în Flask. Read this before working on forecast, backtest, or reorder logic.

## Ops
- **Setup:** `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (adăugate: pandas, numpy, scipy, statsforecast, openpyxl).
- **Import stoc:** `python etl/import_stoc.py docs_input/stoc.xlsx` — coloane detectate flexibil (cod_produs, stoc, opțional sku/furnizor/on_order).
- **Rulează forecast:** `.\tools\run_forecast.ps1 --brand Basilur --horizon 20` sau `--all`.
- **Backtest:** `.\tools\run_backtest.ps1 --brand Basilur` — rolling-origin 3 folds × 13 săpt; raportează WAPE/MASE/bias/service-level.
- **UI:** pornește `Start-Hub.bat` (Windows) sau `tools\Start-Hub.ps1` în PowerShell, apoi `http://localhost:5000/forecast`.

## Reguli business în `brands_config`
- Basilur: lead time 16 săpt + SL 99% + creditare furnizor.
- Toras / Delaviuda: flag `summer_restriction`.
- Restul: lead time 4 săpt.

## Schema
Forecast tables (Faza 1 livrată pe 2026-04-19): `brands_config`, `stock_snapshot`, `forecast_runs`, `forecasts`, `reorder_suggestions`, `forecast_backtests`. Schema created by **migration 0004** — auto-applied on Flask startup (no manual step needed).
