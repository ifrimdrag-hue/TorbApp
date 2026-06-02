# Torb Logistic — AI Operations Platform

Internal AI/analytics platform for Torb Logistic SRL (Romanian FMCG distributor). Provides a management dashboard, sales intelligence, and a demand forecasting engine built on top of 131,898 transaction rows spanning 2024–2026.

---

## Requirements

- Python 3.9+

---

## Setup (macOS / Linux)

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd torb

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the database into place
mkdir -p data
cp /path/to/torb.db data/torb.db
```

---

## Setup (Windows)

```powershell
# 1. Clone and enter the project
git clone <repo-url>
cd torb

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the database into place
mkdir data
copy \path\to\torb.db data\torb.db
```

---

## Running the web app

### macOS / Linux

```bash
./start.sh        # starts Flask on http://localhost:5000
./stop.sh         # stops the server
./restart.sh      # restarts the server
```

### Windows

The `.sh` scripts don't run on Windows. Start the app directly:

```powershell
.venv\Scripts\activate
set FLASK_APP=app/app.py
flask run --port 5000
```

To stop, press `Ctrl+C` in the terminal.

Logs are written to `logs/app.log`.

---

## Forecasting

The forecast engine lives in `forecast/` and is accessible at `/forecast` in the web app.

```bash
# Run forecast for a single brand (horizon = weeks)
python3 -m forecast.run --brand Basilur --horizon 20

# Run forecast for all brands
python3 -m forecast.run --all

# Run backtests (3 rolling-origin folds × 13 weeks each)
python3 -m forecast.backtest --brand Basilur
```

Forecast results and reorder suggestions are stored in `data/torb.db` (tables: `forecasts`, `reorder_suggestions`, `forecast_runs`, `forecast_backtests`).

Business rules per brand (lead times, safety stock, seasonal restrictions) are stored in the `brands_config` table and seeded on first run.

---

## Project structure

```
torb/
├── app/                    # Flask web application
│   ├── app.py              # Routes and Flask entry point
│   ├── db.py               # SQLite connection helper
│   ├── queries.py          # All SQL queries
│   ├── ai.py               # Claude AI assistant integration
│   ├── templates/          # Jinja2 HTML templates
│   └── static/             # CSS, JS assets
├── forecast/               # Demand forecasting module
│   ├── run.py              # CLI entry point
│   ├── backtest.py         # Rolling-origin backtest
│   ├── models.py           # AutoETS + overlays
│   ├── reorder.py          # Reorder suggestion logic
│   ├── export.py           # Excel export (4 sheets)
│   └── schema.py           # SQLite table creation
├── data/                   # SQLite database
│   └── torb.db
├── context/                # Research findings and project context
├── requirements.txt
├── start.sh / stop.sh / restart.sh
├── plan_strategic_5ani.md  # 5-year strategic plan 2026–2030
└── STATUS.md               # Execution status (updated frequently)
```

