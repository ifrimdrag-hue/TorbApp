# Torb Logistic — AI Operations Platform

Internal AI/analytics platform for Torb Logistic SRL (Romanian FMCG distributor). Provides a management dashboard, sales intelligence, demand forecasting, stock synchronisation with eMAG and Shopify, and an AI assistant — built on top of 131,898 transaction rows spanning 2024–2026.

Production: **https://app.robrands.ro**

---

## Requirements

- Python 3.11+
- SQLite 3 (bundled with Python)

---

## Setup

### Windows (primary dev environment)

```powershell
# 1. Clone and enter the project
git clone <repo-url>
cd torbapp

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env
# Edit .env — fill in FLASK_SECRET_KEY and any API credentials you need locally
```

### Linux / macOS (VPS / CI)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

## Environment variables

Copy `.env.example` to `.env` and fill in the values. Variables marked `[SECRET]` must never be committed — on the VPS they are injected by GitHub Actions.

Key groups:

| Variable | Required | Notes |
|---|---|---|
| `FLASK_SECRET_KEY` | Yes | Random hex string |
| `ANTHROPIC_API_KEY` | For AI assistant | Get from console.anthropic.com |
| `SMTP_*` | For password reset emails | Gmail SMTP supported |
| `EMAG_USERNAME` / `EMAG_PASSWORD` | For eMAG stock sync | HTTP Basic Auth |
| `SHOPIFY_CLIENT_ID` / `SHOPIFY_CLIENT_SECRET` | For Shopify stock sync | OAuth client credentials |
| `SHOPIFY_SHOP_DOMAIN` / `SHOPIFY_LOCATION_ID` | For Shopify stock sync | Non-secret, in .env.example |

---

## Running the web app

### Windows

```powershell
# Option A — PowerShell hub script (recommended)
.\tools\Start-Hub.ps1

# Option B — bat launcher
Start-Hub.bat

# Option C — directly
.venv\Scripts\activate
flask --app app/app.py run --port 5000
```

### Linux / macOS

```bash
source .venv/bin/activate
flask --app app/app.py run --port 5000
```

App is available at **http://localhost:5000**. Logs are written to `logs/app.log`.

---

## Database

The SQLite database lives at `data/torb.db`. To rebuild from scratch from the Excel source files in `docs_input/`:

```bash
python etl/import_to_sqlite.py       # main transaction data
python etl/import_stoc.py docs_input/stoc.xlsx   # stock snapshot
python etl/import_preturi.py         # pricing
```

Database migrations run automatically on Flask startup (`app/migrate.py`).

---

## Forecasting

The demand forecast engine lives in `forecast/` and is accessible at `/forecast` in the web app.

```powershell
# Run forecast for a single brand (horizon = weeks ahead)
.\tools\run_forecast.ps1 --brand Basilur --horizon 20

# Run forecast for all brands
.\tools\run_forecast.ps1 --all

# Rolling-origin backtest (3 folds × 13 weeks)
.\tools\run_backtest.ps1 --brand Basilur
```

Results are stored in `data/torb.db` (tables: `forecasts`, `reorder_suggestions`, `forecast_runs`, `forecast_backtests`). Business rules per brand (lead times, safety stock, seasonal restrictions) are in the `brands_config` table.

---

## Stock synchronisation

Unified UI at `/stocuri` — switch between eMAG and Shopify via radio buttons.

- **eMAG**: upload the stock report Excel file → preview diff → sync via eMAG Marketplace API v4.5.1
- **Shopify**: upload the same report → preview diff → sync via Shopify GraphQL Admin API (2025-04), OAuth client credentials grant

Request logs (last 20 calls each): `logs/emag_req.json`, `logs/shopify_req.json`.

---

## Tests

```bash
pytest tests/ -v
```

73 tests covering: Flask routes, auth, stock blueprints, ETL parsers, forecast engine, bonus calculator.

---

## Working with Claude Code (AI-assisted development)

This project ships a Claude Code skill in `.claude/skills/` that all collaborators with [Claude Code](https://claude.ai/code) installed will get automatically.

### `BUG:` — bug fix with mandatory regression test

Prefix any message to Claude with `BUG:` and describe the problem:

```
BUG: the bonus calculator shows the wrong total when an agent has zero sales in one month
```

Claude will:
1. Locate the affected code and root cause
2. Check whether an existing test would have caught this
3. Write a **regression test first** (it must fail before the fix)
4. Apply the fix
5. Verify the test turns green
6. Run the full suite (`pytest tests/ -v`) — must be 100% green
7. Commit the fix and the test together

**Why this matters:** every bug that goes through this workflow leaves a permanent test that guards that code path. Over time the suite becomes a complete map of every bug that has ever existed, and CI (`ruff` + `pytest`) prevents any of them from coming back silently before reaching production.

The skill lives at `.claude/skills/bug-fix-with-coverage/SKILL.md` — read it for the full workflow detail.

---

## Deployment (CI/CD)

Push to `main` triggers GitHub Actions (`.github/workflows/deploy_VPS.yml`):

1. **lint** — `ruff check .`
2. **test** — `pytest tests/`
3. **security** — `pip-audit` (blocking — a known vulnerability in dependencies fails the pipeline)
4. **deploy** — SSH to VPS, `git reset --hard origin/main`, inject secrets into `.env`, restart `torb-py` systemd service
5. **smoke-test** — curl checks against `https://app.robrands.ro`

Secrets required in GitHub Actions: `FLASK_SECRET_KEY`, `ANTHROPIC_API_KEY`, `EMAG_USERNAME`, `EMAG_PASSWORD`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `VPS_HOST`, `VPS_USERNAME`, `VPS_SSH_KEY`.

### Emergency rollback

If a blocking issue is found in production and the technical team is unavailable, any GitHub collaborator with write access can roll back to the previous version without touching code or a terminal:

1. Go to the repository on GitHub
2. Click **Actions** → **Rollback Production to Previous Version**
3. Click **Run workflow** (top-right)
4. Type `ROLLBACK` in the confirmation field and click **Run workflow**

The workflow will revert the VPS to the previous commit, restart the service, and run smoke tests to confirm it came back up. If the smoke tests fail, the workflow exits with an error — contact the technical team immediately in that case.

> **Note:** database migrations are not reversed by a rollback (they are additive and safe to leave in place). Only the application code reverts.

---

## Project structure

```
torbapp/
├── app/                        # Flask web application
│   ├── app.py                  # Application factory and blueprint registration
│   ├── config.py               # pydantic-settings config (reads .env)
│   ├── migrate.py              # Auto-run DB migrations on startup
│   ├── blueprints/             # Route handlers (one file per feature area)
│   │   ├── auth.py             # Login, logout, password reset, admin user management
│   │   ├── analytics.py        # Dashboard, sales reports
│   │   ├── forecast.py         # Forecast UI and API
│   │   ├── stocuri_emag.py     # eMAG stock sync routes + unified /stocuri page
│   │   ├── stocuri_shopify.py  # Shopify stock sync routes
│   │   ├── pricing.py          # Pricing management
│   │   ├── bonus.py            # Bonus calculator
│   │   └── ...
│   ├── automations/            # Business logic modules (not Flask-aware)
│   │   ├── stocuri_emag/       # eMAG API client, orchestrator, request logger
│   │   ├── stocuri_shopify/    # Shopify GraphQL client, orchestrator, request logger
│   │   └── ...
│   ├── templates/              # Jinja2 HTML templates
│   └── static/                 # CSS, JS assets
│   ├── forecast/               # Demand forecasting package
│   │   ├── run.py              # CLI pipeline (use tools/run_forecast.ps1)
│   │   ├── backtest.py         # Rolling-origin backtest
│   │   ├── models.py           # AutoETS + seasonal overlays
│   │   ├── reorder.py          # Reorder suggestion logic
│   │   ├── schema.py           # Forecast table DDL + DB_PATH
│   │   ├── forecast_logic.py   # Procurement suggestion logic (Flask-facing)
│   │   ├── forecast_engine.py  # ForecastEngine data class
│   │   └── forecast_agent.py   # AI procurement agent
├── etl/                        # Data pipeline scripts (run from project root)
│   ├── import_to_sqlite.py     # Main transaction data import
│   ├── import_stoc.py          # Stock snapshot import
│   ├── import_preturi.py       # Pricing import
│   └── rebuild_db.py           # Full DB rebuild
├── tests/                      # pytest test suite
├── tools/                      # Windows launcher scripts
│   └── Start-Hub.ps1
├── context/                    # Project research, reference docs and strategic files
│   ├── plan_strategic_5ani.md  # 5-year strategic plan 2026–2030
│   ├── STATUS.md               # Current execution status
│   ├── torb_background.md      # Company background research
│   └── ...                     # Business overview, AI opportunities, risks, data file map
├── docs/                       # Implementation plans, analysis and user manuals
│   ├── plans/                  # Implementation plans
│   ├── analysis/               # Analysis documents
│   ├── superpowers/            # AI-generated specs and plans
│   └── manuals/                # End-user manuals (PDF + Typst source)
├── .claude/skills/             # Shared Claude Code skills (auto-loaded for all collaborators)
│   └── bug-fix-with-coverage/  # BUG: prefix — fix + regression test workflow
├── migrations/                 # Versioned DB migration files (applied on startup)
├── data/                       # SQLite database (gitignored)
├── logs/                       # App and request logs (gitignored)
├── docs_input/                 # Source Excel/CSV files (gitignored)
├── .env.example                # Environment variable template
├── requirements.txt
└── Start-Hub.bat               # Windows quick launcher
```
