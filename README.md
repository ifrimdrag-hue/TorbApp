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

```bash
# Run forecast for a single brand (horizon = weeks ahead)
python -m forecast.run --brand Basilur --horizon 20

# Run forecast for all brands
python -m forecast.run --all

# Rolling-origin backtest (3 folds × 13 weeks)
python -m forecast.backtest --brand Basilur
```

Results are stored in `data/torb.db` (tables: `forecasts`, `reorder_suggestions`, `forecast_runs`, `forecast_backtests`). Business rules per brand (lead times, safety stock, seasonal restrictions) are in the `brands_config` table.

---

## Stock synchronisation

Unified UI at `/stocuri` — switch between eMAG and Shopify via radio buttons.

- **eMAG**: upload the stock report Excel file → preview diff → sync via eMAG Marketplace API v3
- **Shopify**: upload the same report → preview diff → sync via Shopify GraphQL Admin API (2025-04), OAuth client credentials grant

Request logs (last 20 calls each): `logs/emag_req.json`, `logs/shopify_req.json`.

---

## Tests

```bash
pytest tests/ -v
```

67 tests covering: Flask routes, auth, stock blueprints, ETL parsers, forecast engine, bonus calculator.

---

## Deployment (CI/CD)

Push to `main` triggers GitHub Actions (`.github/workflows/deploy_VPS.yml`):

1. **lint** — `ruff check .`
2. **test** — `pytest tests/`
3. **security** — `pip-audit` (non-blocking)
4. **deploy** — SSH to VPS, `git reset --hard origin/main`, inject secrets into `.env`, restart `torb-py` systemd service
5. **smoke-test** — curl checks against `https://app.robrands.ro`

Secrets required in GitHub Actions: `FLASK_SECRET_KEY`, `ANTHROPIC_API_KEY`, `EMAG_USERNAME`, `EMAG_PASSWORD`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `VPS_HOST`, `VPS_USERNAME`, `VPS_SSH_KEY`.

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
├── forecast/                   # Demand forecasting CLI package
│   ├── run.py                  # CLI entry point
│   ├── backtest.py             # Rolling-origin backtest
│   ├── models.py               # AutoETS + seasonal overlays
│   ├── reorder.py              # Reorder suggestion logic
│   └── schema.py               # Forecast table DDL
├── etl/                        # Data pipeline scripts (run from project root)
│   ├── import_to_sqlite.py     # Main transaction data import
│   ├── import_stoc.py          # Stock snapshot import
│   ├── import_preturi.py       # Pricing import
│   └── rebuild_db.py           # Full DB rebuild
├── tests/                      # pytest test suite
├── tools/                      # Windows launcher scripts
│   └── Start-Hub.ps1
├── context/                    # Project research and reference docs
├── data/                       # SQLite database (gitignored)
├── logs/                       # App and request logs (gitignored)
├── docs_input/                 # Source Excel/CSV files (gitignored)
├── .env.example                # Environment variable template
├── requirements.txt
├── plan_strategic_5ani.md      # 5-year strategic plan 2026–2030
└── STATUS.md                   # Current execution status
```
