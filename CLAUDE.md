# Torb Logistic — Project Context

## Code quality rules (enforced in CI)
- **Linter**: `ruff` — all Python must pass `ruff check .` with zero errors before commit.
- **Auto-fix hook**: a `PostToolUse` hook in `~/.claude/settings.json` runs `ruff check --fix --quiet` on every `.py` file Claude writes or edits. No manual lint pass needed.
- **Forbidden patterns**: `E401` (multiple imports), `E402` (module-level import not at top), `E701/E702` (compound statements), `E722` (bare except), `E741` (ambiguous names `l`, `O`, `I`), `F401` (unused imports), `F841` (unused variables).

## What this project is
AI consulting for Torb Logistic SRL, a Romanian FMCG distributor. Goal: identify and implement AI/agentic automation opportunities to optimize business operations.

## Key facts (do not re-derive from scratch)
- Torb distributes **12 brands** (not just Basilur). Main ones: Basilur 31%, Toras 22%, Leonex 20%, Celmar 13%.
- 2025 total revenue: ~15M RON across 3,297 clients
- Biggest risk: Bogdan Dragnea = 55.6% of all sales. Kaufland = 41.4% of revenue.
- The reporting dashboards are well-designed templates but **contain no data** — the core gap is a missing data pipeline from raw transactions to management reports.

## File map
- `context/torb_background.md` — company background research (note: incomplete on brand portfolio)
- `docs_input/` — all Excel data files. See memory for detailed file map.
- `docs_input/vanzari_01.03.2026.xlsx` — main sales database (Baza sheet = raw transactions)
- `docs_input/bonusare_torb_structura_echipa.xlsx` — team structure + KPI/bonus system
- `docs_input/TORB_Dashboard_Managerial_FMCG.xlsx` — executive dashboard template (empty, needs pipeline)
- `docs_input/model_livrabil_plan_vanzari_RON.xlsx` — individual sales plan template

## SQLite database
`data/torb.db` — 131,898 transaction rows, 2024-01-03 → 2026-03-31.
Main table: `tranzactii` (31 columns). Useful views: `v_vanzari_an_furnizor`, `v_vanzari_luna_agent`, `v_vanzari_luna_client`, `v_top_sku`, `v_clienti`.
To rebuild: `python etl/import_to_sqlite.py`

Forecast tables (Faza 1 livrată pe 2026-04-19): `brands_config`, `stock_snapshot`, `forecast_runs`, `forecasts`, `reorder_suggestions`, `forecast_backtests`. Schema created by **migration 0004** — auto-applied on Flask startup (no manual step needed).

## Forecast module
Localizare: `app/forecast/` + pagina `/forecast` în Flask.

- **Setup:** `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (adăugate: pandas, numpy, scipy, statsforecast, openpyxl).
- **Import stoc:** `python etl/import_stoc.py docs_input/stoc.xlsx` — coloane detectate flexibil (cod_produs, stoc, opțional sku/furnizor/on_order).
- **Rulează forecast:** `.\tools\run_forecast.ps1 --brand Basilur --horizon 20` sau `--all`.
- **Backtest:** `.\tools\run_backtest.ps1 --brand Basilur` — rolling-origin 3 folds × 13 săpt; raportează WAPE/MASE/bias/service-level.
- **UI:** pornește `Start-Hub.bat` (Windows) sau `tools\Start-Hub.ps1` în PowerShell, apoi `http://localhost:5000/forecast`.
- **Reguli business în `brands_config`:** Basilur lead time 16 săpt + SL 99% + creditare furnizor; Toras/Delaviuda au flag `summer_restriction`; restul lead time 4 săpt.

## How to read Excel files
Use `openpyxl` with `read_only=True` for large files.
```python
import openpyxl
wb = openpyxl.load_workbook('file.xlsx', data_only=True, read_only=True)
```

## Where to start each session

**Citește obligatoriu la începutul fiecărei sesiuni:**
1. `context/plan_strategic_5ani.md` — planul strategic 2026–2030 (teza, piloni, roadmap, financial model). Nu reinterpreta strategia de la zero — pleacă de aici.
2. `context/STATUS.md` — starea curentă a execuției. Ce s-a livrat, ce e în lucru, ce e blocat, care e următorul pas. **Actualizează acest fișier la fiecare schimbare de stare**, nu la fiecare discuție.
3. Restul fișierelor din `context/` — findings de research (overview business, riscuri, oportunități AI, reference fișiere de date).
4. `.claude/project_knowledge.md` — durable technical notes: deploy pipeline & secrets, Shopify sync internals, Romanian-encoding rules for `.py` files, Typst manual rules, tech-debt backlog. Read before working on any of those areas.

**Separarea responsabilităților:**
- `context/plan_strategic_5ani.md` = ce vrem să realizăm (stabil, revizuit trimestrial).
- `context/STATUS.md` = unde suntem acum (volatil, actualizat des).
- `context/*.md` + memorie = fapte durabile despre proiect.

Actual #1 open question: bonusarea automată lunară (pasul 5 din `context/STATUS.md`, deadline 31 mai 2026 — întârziat) și validarea forecast Basilur cu owner-ul.

## Project Directory Structure

All new files must follow this layout. Never add `.py` files to root.

| Directory | What goes here |
|-----------|---------------|
| `app/` | Flask web application only: routes, db, queries, AI helpers, Excel/PPT exports, migrations |
| `etl/` | Data pipeline scripts: `import_*.py`, `rebuild_*.py`, `init_*.py`, `update_*.py` |
| `app/forecast/` | Forecast package: statistical engine, data queries, CLI, Flask-facing logic, AI agent |
| `tools/` | Windows launcher scripts (`Start-Hub.ps1`); `Start-Hub.bat` is at project root |
| `tests/` | pytest test files |
| `context/` | Project research, reference markdown files, strategic docs (`plan_strategic_5ani.md`, `STATUS.md`, `torb_background.md`) |
| `docs/` | Implementation plans (`plans/`), analysis docs (`analysis/`), AI-generated specs (`superpowers/`), user manuals (`manuals/`) |
| `docs_input/` | Input Excel/CSV data files (never committed, gitignored) |
| `data/` | SQLite database and generated outputs (gitignored) |
| Root | Config/doc files only: `requirements.txt`, `.gitignore`, `.env.example`, `CLAUDE.md`, `README.md`, `CHANGELOG.md`, `Start-Hub.bat` |

### Rules when creating new files

- New Flask route or feature module → `app/`
- New import from Excel/ERP/supplier file → `etl/`
- New Windows launcher script → `tools/`
- New forecast model, backtest, or forecast CLI tool → `forecast/`
- New pytest test → `tests/`

### Import path note for etl/ scripts

ETL scripts use CWD-relative paths (`"data/torb.db"`, `"docs_input/..."`). Always run them from the project root:
```
python etl/import_preturi.py
```
If a script needs to import sibling modules from `etl/`, add at the top:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```
