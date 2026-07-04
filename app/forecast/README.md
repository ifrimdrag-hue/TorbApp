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

`forecast_config` (migration 0017): generic key/value table for tuning params, seeded with hard defaults. See "Client × article model" below.

## Client × article model (2026-07-04, behind a toggle, default OFF)

New procurement-forecast core in `app/forecast/pair_engine.py` — computes demand per **client × article pair** instead of per-SKU average, which fixes the old model's tendency to keep reordering delisted/declining SKUs (backlog item B4). Pure, unit-tested functions (`tests/test_pair_engine.py`):

- `build_window(first_sale, today, window_months)` — per-pair history window: `[max(first_sale month, today − window_months), last closed month]` (spec §4.1).
- `monthly_mean_with_zeros(pair_months, window)` — mean over the window with missing months counted as zero, so pairs with a partial or ended run don't retain their old average forever (spec §4.2).
- `seasonal_index(article_month_qty, min_history_months, cap_lo, cap_hi)` — article-level seasonal index, gated off (flat 1.0) below `sezonalitate_min_luni` (default 24) months of history, capped to `[indice_sezonier_min, indice_sezonier_max]` (default `[0.2, 5.0]`) (spec §4.3).
- `delisting_status(purchase_dates, today, min_days, mult)` — marks a pair `SUSPECT` when `days_since_last_purchase > max(min_days, mult × mean_interval_between_purchases)` — an adaptive threshold so a quarterly-ordering client isn't flagged at 5 months (spec §5.1). `SUSPECT` pairs are excluded from the article's forecast (no slow zero-dilution).
- `article_monthly_profiles(furnizor, params, today=None)` — aggregates all `ACTIVE` (non-suspect) pairs for a supplier into per-article `{ro, export, total}` monthly profiles (12-key dicts) plus `cod_produs`, `suspects` (list of delisting-suspect clients), `n_active`, `n_suspect` (spec §2).

### Config — `forecast_config` table + `/forecast/setari`

`app/forecast/config.py` exposes `get_params()` (defaults merged with DB overrides) / `set_param(key, value)`. Defaults (spec §9), also seeded by migration 0017:

| Key | Default | Meaning |
|---|---|---|
| `fereastra_luni` | 36 | History window (months) for the pair mean |
| `sezonalitate_min_luni` | 24 | Min months of article history before seasonality applies |
| `indice_sezonier_min` / `_max` | 0.2 / 5.0 | Seasonal index cap |
| `prag_delistare_zile` | 180 | Minimum days-since-last-purchase floor for SUSPECT |
| `prag_delistare_mult` | 3 | Multiplier on mean purchase interval for SUSPECT |
| `coef_siguranta` | 0.25 | Safety-stock coefficient (× monthly forecast) |
| `perioada_acoperire_luni` | 1 | Coverage period (months) for `split_with_safety` |
| `confirmare_delistare_zile`, `taiere_inactiv_luni`, `oos_prag_pct`, `rampup_luni`, `plafon_varf_initial`, `factor_marime_min`/`_max` | — | Reserved for deferred lifecycle/ramp-up/OOS logic (see below); not yet consumed by any code path |

The "Parametri forecast" card on `/forecast/setari` edits these live via `GET`/`POST /api/forecast/config`.

### Order formula (partial — spec §8)

`forecast_logic.split_with_safety(monthly_ro, monthly_export, lead_days, available, base_ro, base_export, coef, coverage_days, buc_cutie)` — like the existing `_ro_hu_split` (stock covers RO demand first, surplus goes to export), but adds `safety = coef × monthly_forecast` to each market's demand before subtracting available stock, then rounds each suggestion up to the next full bax via `produse.buc_cutie` (`round_up_to_bax`). **Not implemented:** MOQ floor (deferred, see decision 6 below).

### Wiring — `?model=nou` / `?compare=1`

Both entry points default to the unchanged legacy behaviour; the new model is opt-in only:

- `forecast_logic.build_suggestion(furnizor, ..., model="actual"|"nou")` — Suggest tab. `model="nou"` swaps `_monthly_sales_by_sku` for `pair_engine.article_monthly_profiles` and `_ro_hu_split` for `split_with_safety`; adds `n_suspect`/`suspects`/`safety_ro`/`safety_export` to each item.
- `queries.forecast_stoc_extended(..., model="actual"|"nou")` — Stoc tab, same swap.
- `/forecast?model=nou` — switches the whole page to the new model.
- `/forecast?compare=1` — validation view: renders the **old** model as the base rows, then runs the new model alongside and attaches `suggested_ro_nou`/`suggested_hu_nou` per SKU so old-vs-new can be diffed on screen before flipping the default. Use this to validate before changing the `model` default in `app/blueprints/forecast.py`.
- UI (`forecast.html`): model toggle control, "Suspect delistare" badge (from `n_suspect`/`suspects`), a "fără ajustare (<24 luni)" seasonality marker when the gate hasn't opened yet, and a suggestion-transparency popover showing the demand/safety-stock breakdown.

### Deferred spec items — need owner decisions (`docs/decision.html`, items 5–10)

Not implemented; blocked on data availability or a product decision. Each maps to a numbered card in `docs/decision.html` ("Runda 2 · Noul model de forecast"):

| # | Spec ref | What's blocked |
|---|---|---|
| 5 | §4.4 | Out-of-stock month exclusion from the mean — needs daily/monthly stock history to detect ruptures; not yet distinguished from genuine zero-demand months |
| 6 | §8 | MOQ floor per supplier/article (bax rounding is implemented; the minimum-order-quantity floor is not) |
| 7 | §5 | Full DELISTAT/REACTIVAT lifecycle — who confirms a `SUSPECT` pair is a real delisting vs. a pause (auto-confirm after `confirmare_delistare_zile`, manual override) |
| 8 | §6 | New-listing ramp-up — initial estimate for a client×article pair with no history, definition of "comparable clients" |
| 9 | — | Whether to keep the RO/Export HU suggestion split in the new model (currently kept) |
| 10 | §10 | Nightly batch recalculation vs. on-demand (currently on-demand, same as legacy) |

Tests: `tests/test_pair_engine.py`, `tests/test_forecast_reorder.py`, `tests/test_forecast_config.py`, `tests/test_forecast_routes.py`.
