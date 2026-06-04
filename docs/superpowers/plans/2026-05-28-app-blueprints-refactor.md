# app.py Blueprints Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Break ClaudeTorb's 2,241-line `app/app.py` into focused Flask blueprints and a `create_app()` factory, so the app is ready to receive ClaudeTorbStock blueprints during unification without touching existing functionality.

**Architecture:** Extract routes into `app/blueprints/` domain files one group at a time, using the existing smoke-test suite as a regression guard after every move. The factory pattern (`create_app()`) is introduced last, after all routes are already in blueprints.

**Tech Stack:** Python 3.9+, Flask 3, Flask-Login, Flask-WTF (CSRFProtect), pytest

---

## File Map

Files that will be **created**:

| File | Responsibility |
|------|---------------|
| `app/blueprints/__init__.py` | Empty — marks the package |
| `app/blueprints/auth.py` | Moved from `app/auth.py` (auth_bp + admin_bp) |
| `app/blueprints/analytics.py` | dashboard, team, agent, clients, client, products, brand, ask |
| `app/blueprints/bonus.py` | bonus, bonus_simulator, api_bonus_*, exports |
| `app/blueprints/pricing.py` | preturi, conditii, api_preturi_*, api_conditii_*, api_termene |
| `app/blueprints/forecast.py` | forecast, comenzi, upload, actualizare-date, clienti-export |
| `app/blueprints/reports.py` | profitabilitate, produs, raportare-basilur, export_ppt_*, export_excel |
| `wsgi.py` | Production entry point (`app = create_app()`) |

Files that will be **modified**:

| File | Change |
|------|--------|
| `app/app.py` | Routes deleted one group at a time; factory wrapper added last |
| `app/templates/base.html` | `url_for` nav links get blueprint prefixes |
| `tests/conftest.py` | `flask_app` fixture updated to use `create_app()` |

Files that will be **deleted**:

| File | Reason |
|------|--------|
| `app/auth.py` | Content moved to `app/blueprints/auth.py` |

---

## Task 1 — Create `blueprints/` package and move `auth.py`

**Files:**
- Create: `app/blueprints/__init__.py`
- Create: `app/blueprints/auth.py` (content from `app/auth.py`)
- Modify: `app/app.py:24` (update import)
- Delete: `app/auth.py`

- [ ] **Step 1: Confirm the baseline tests pass**

```
cd c:\MINE\ClaudeTorb
python -m pytest tests/test_flask_routes.py -v
```

Expected: all tests pass (green). If any fail, fix them before proceeding.

- [ ] **Step 2: Create the blueprints package**

Create `app/blueprints/__init__.py` — empty file:

```python
```

- [ ] **Step 3: Copy `app/auth.py` to `app/blueprints/auth.py`**

The file content is identical. No changes to the code inside — just the location changes.

```
copy c:\MINE\ClaudeTorb\app\auth.py c:\MINE\ClaudeTorb\app\blueprints\auth.py
```

- [ ] **Step 4: Update the import in `app/app.py` line 24**

Change:
```python
from auth import admin_bp, auth_bp, csrf, login_manager
```

To:
```python
from blueprints.auth import admin_bp, auth_bp, csrf, login_manager
```

(`app/` is already on sys.path via the insert at line 11, so `blueprints.auth` resolves to `app/blueprints/auth.py`.)

- [ ] **Step 5: Delete the old `app/auth.py`**

```
del c:\MINE\ClaudeTorb\app\auth.py
```

- [ ] **Step 6: Run the tests**

```
python -m pytest tests/test_flask_routes.py -v
```

Expected: all tests pass (same result as Step 1).

- [ ] **Step 7: Commit**

```bash
git add app/blueprints/__init__.py app/blueprints/auth.py app/app.py
git rm app/auth.py
git commit -m "refactor: create blueprints/ package, move auth.py into it"
```

---

## Task 2 — Extract `analytics` blueprint

Routes moved: `dashboard`, `team`, `agent_detail`, `clients`, `client_detail`, `products`, `brand_detail`, `ask`, `api_ask`
Helpers moved: `_delta_pct`, `_build_trend_series`

**Files:**
- Create: `app/blueprints/analytics.py`
- Modify: `app/app.py` (register blueprint, remove moved functions)
- Modify: `app/templates/base.html` and any template with nav `url_for` calls

- [ ] **Step 1: Add the new routes to `tests/test_flask_routes.py`**

The routes already exist in `MAIN_ROUTES` — no new tests needed. Confirm the list covers `/`, `/team`, `/clients`, `/products`, `/ask`.

- [ ] **Step 2: Run the tests (baseline)**

```
python -m pytest tests/test_flask_routes.py -v
```

Expected: pass.

- [ ] **Step 3: Create `app/blueprints/analytics.py`**

```python
import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
import queries
import db

analytics_bp = Blueprint('analytics', __name__)


def _delta_pct(cy, py):
    if not py:
        return None
    return round((cy / py - 1) * 100, 1)


def _build_trend_series(trend_rows):
    """Convert trend query rows to {year: [12 values]} dict."""
    by_year = {}
    for row in trend_rows:
        yr = row['an']
        if yr not in by_year:
            by_year[yr] = [0] * 12
        luna = row['luna']
        if luna:
            by_year[yr][int(luna) - 1] = row['val_neta'] or 0
    return by_year
```

Then cut and paste the following functions from `app/app.py` verbatim into this file, changing **only** the decorator prefix from `@app.route` to `@analytics_bp.route`:

| Function | Current line in app.py |
|----------|----------------------|
| `dashboard()` | 260 |
| `team()` | 312 |
| `agent_detail(name)` | 325 |
| `clients()` | 369 |
| `client_detail(cod_client)` | 399 |
| `products()` | 432 |
| `brand_detail(furnizor)` | 452 |
| `ask()` | 497 |
| `api_ask()` | 503 |

Delete the same functions (and `_delta_pct`, `_build_trend_series`) from `app/app.py`.

- [ ] **Step 4: Register the blueprint in `app/app.py`**

Add after the existing blueprint registrations (lines 74–75):

```python
from blueprints.analytics import analytics_bp
app.register_blueprint(analytics_bp)
```

- [ ] **Step 5: Find and update all `url_for` calls that reference the moved functions**

Run:
```
grep -rn "url_for(" app/templates/ app/app.py --include="*.html" --include="*.py"
```

For every occurrence of `url_for('dashboard')`, `url_for('team')`, `url_for('agent_detail')`, `url_for('clients')`, `url_for('client_detail')`, `url_for('products')`, `url_for('brand_detail')`, `url_for('ask')`, change to the blueprint-prefixed form:

| Old | New |
|-----|-----|
| `url_for('dashboard')` | `url_for('analytics.dashboard')` |
| `url_for('team')` | `url_for('analytics.team')` |
| `url_for('agent_detail', ...)` | `url_for('analytics.agent_detail', ...)` |
| `url_for('clients')` | `url_for('analytics.clients')` |
| `url_for('client_detail', ...)` | `url_for('analytics.client_detail', ...)` |
| `url_for('products')` | `url_for('analytics.products')` |
| `url_for('brand_detail', ...)` | `url_for('analytics.brand_detail', ...)` |
| `url_for('ask')` | `url_for('analytics.ask')` |

- [ ] **Step 6: Run the tests**

```
python -m pytest tests/test_flask_routes.py -v
```

Expected: all tests pass. A `BuildError` or 500 on any route means a `url_for` call was missed — grep again and fix.

- [ ] **Step 7: Commit**

```bash
git add app/blueprints/analytics.py app/app.py app/templates/
git commit -m "refactor: extract analytics blueprint (dashboard, team, agent, clients, products, brand, ask)"
```

---

## Task 3 — Extract `bonus` blueprint

Routes moved: `bonus`, `bonus_simulator`, `api_bonus_agent_data`, `api_bonus_simulate`, `bonus_export`, `bonus_simulator_export`

**Files:**
- Create: `app/blueprints/bonus.py`
- Modify: `app/app.py`
- Modify: templates with `url_for('bonus')` etc.

- [ ] **Step 1: Run the tests (baseline)**

```
python -m pytest tests/test_flask_routes.py -v
```

Expected: pass.

- [ ] **Step 2: Create `app/blueprints/bonus.py`**

```python
from flask import Blueprint, render_template, request, jsonify, send_file
import queries
import db
from bonus_calc import PRESETS, SIM_MONTHS, MONTHS_RO as BONUS_MONTHS_RO, STRATEGIC_BRANDS, STRATEGIC_WEIGHTS_DEFAULT, simulate
from excel_export import send_excel, timestamped_filename

bonus_bp = Blueprint('bonus', __name__)
```

Then cut and paste from `app/app.py`, changing `@app.route` → `@bonus_bp.route`:

| Function | Current line in app.py |
|----------|----------------------|
| `bonus()` | 570 |
| `bonus_simulator()` | 653 |
| `api_bonus_agent_data(name)` | 675 |
| `api_bonus_simulate()` | 714 |
| `bonus_export()` | 736 |
| `bonus_simulator_export()` | 779 |

Delete the same functions from `app/app.py`.

- [ ] **Step 3: Register the blueprint in `app/app.py`**

```python
from blueprints.bonus import bonus_bp
app.register_blueprint(bonus_bp)
```

- [ ] **Step 4: Update `url_for` references**

```
grep -rn "url_for(" app/templates/ app/app.py --include="*.html" --include="*.py"
```

| Old | New |
|-----|-----|
| `url_for('bonus')` | `url_for('bonus.bonus')` |
| `url_for('bonus_simulator')` | `url_for('bonus.bonus_simulator')` |
| `url_for('bonus_export')` | `url_for('bonus.bonus_export')` |
| `url_for('bonus_simulator_export')` | `url_for('bonus.bonus_simulator_export')` |

- [ ] **Step 5: Run the tests**

```
python -m pytest tests/test_flask_routes.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/blueprints/bonus.py app/app.py app/templates/
git commit -m "refactor: extract bonus blueprint"
```

---

## Task 4 — Extract `pricing` blueprint

Routes moved: `preturi`, `preturi_sku`, `api_preturi_landing`, `api_preturi_vanzare`, `api_preturi_produs`, `api_preturi_curs`, `api_preturi_simuleaza`, `conditii`, `api_conditii_create`, `api_conditii_update`, `api_conditii_delete`, `api_termene_create`, `api_termene_delete`

**Files:**
- Create: `app/blueprints/pricing.py`
- Modify: `app/app.py`, templates

- [ ] **Step 1: Run the tests (baseline)**

```
python -m pytest tests/test_flask_routes.py -v
```

Expected: pass.

- [ ] **Step 2: Create `app/blueprints/pricing.py`**

```python
from flask import Blueprint, render_template, request, jsonify
import queries
import db

pricing_bp = Blueprint('pricing', __name__)
```

Cut and paste from `app/app.py`, changing `@app.route` → `@pricing_bp.route`:

| Function | Current line in app.py |
|----------|----------------------|
| `preturi()` | 816 |
| `preturi_sku(sku)` | 838 |
| `api_preturi_landing()` | 853 |
| `api_preturi_vanzare()` | 870 |
| `api_preturi_produs()` | 884 |
| `api_preturi_curs()` | 898 |
| `api_preturi_simuleaza()` | 909 |
| `conditii()` | 937 |
| `api_conditii_create()` | 963 |
| `api_conditii_update(id)` | 979 |
| `api_conditii_delete(id)` | 995 |
| `api_termene_create()` | 1002 |
| `api_termene_delete(id)` | 1014 |

Delete the same functions from `app/app.py`.

- [ ] **Step 3: Register in `app/app.py`**

```python
from blueprints.pricing import pricing_bp
app.register_blueprint(pricing_bp)
```

- [ ] **Step 4: Update `url_for` references**

```
grep -rn "url_for(" app/templates/ app/app.py --include="*.html" --include="*.py"
```

| Old | New |
|-----|-----|
| `url_for('preturi')` | `url_for('pricing.preturi')` |
| `url_for('preturi_sku', ...)` | `url_for('pricing.preturi_sku', ...)` |
| `url_for('conditii')` | `url_for('pricing.conditii')` |

- [ ] **Step 5: Run the tests**

```
python -m pytest tests/test_flask_routes.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/blueprints/pricing.py app/app.py app/templates/
git commit -m "refactor: extract pricing blueprint (preturi + conditii)"
```

---

## Task 5 — Extract `forecast` blueprint

This is the largest group. Routes also own the async job globals (`_import_job`, `_upload_jobs`) and the `_log_import` helper, which move into the blueprint file.

Routes moved: `forecast`, `forecast_setari`, `api_forecast_tara_save`, `api_forecast_tara_delete`, `api_forecast_client_save`, `api_forecast_client_toggle`, `api_forecast_termene_save`, `api_forecast_suggest`, `api_actualizare_date`, `api_actualizare_date_status`, `api_import_log`, `api_upload`, `api_upload_status`, `api_forecast_refresh_stoc`, `api_forecast_sku_clients`, `api_comenzi_drafts`, `api_comanda_create`, `api_clienti_export_list`, `api_clienti_export_add`, `api_clienti_export_delete`, `api_clienti_search`, `api_comanda_get`, `api_comanda_update`, `api_comanda_delete`, `api_comanda_line_add`, `api_comanda_line_update`, `api_comanda_line_delete`, `api_comanda_status`, `api_termene_upsert`, `export_comanda`, `import_comanda_lines`, `api_forecast_chat`, `api_comanda_avanseaza`

**Files:**
- Create: `app/blueprints/forecast.py`
- Modify: `app/app.py`, templates

- [ ] **Step 1: Run the tests (baseline)**

```
python -m pytest tests/test_flask_routes.py -v
```

Expected: pass.

- [ ] **Step 2: Create `app/blueprints/forecast.py`**

```python
import os
import threading
import logging
import sqlite3 as _sq
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, send_file
import queries
import db
import forecast_logic
from excel_export import send_excel, timestamped_filename
import paths

logger = logging.getLogger(__name__)

forecast_bp = Blueprint('forecast', __name__)

# Async job state — owned by this module since only forecast routes use it
_import_job: dict = {'status': 'idle', 'message': ''}
_import_lock = threading.Lock()
_upload_jobs: dict = {}
_upload_jobs_lock = threading.Lock()


def _log_import(tip: str, fisier: str, randuri, durata_s: float, status: str, mesaj: str = ''):
    """Write an import_log record from a background thread (uses its own connection)."""
    try:
        conn = _sq.connect(paths.DB_PATH)
        conn.execute(
            "INSERT INTO import_log (tip, fisier, randuri, durata_s, status, mesaj) VALUES (?,?,?,?,?,?)",
            (tip, fisier, randuri, round(durata_s, 2), status, mesaj)
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.warning("_log_import DB write failed for tip=%s fisier=%s", tip, fisier, exc_info=True)
```

Then cut and paste the following functions from `app/app.py`, changing `@app.route` → `@forecast_bp.route`. Also cut `_import_job`, `_import_lock`, `_upload_jobs`, `_upload_jobs_lock`, and `_log_import` from `app/app.py`.

Note: `_log_import` in app.py builds the DB path inline with `os.path.dirname(...)` — replace that path construction with `paths.DB_PATH` (already imported above).

| Function | Current line in app.py |
|----------|----------------------|
| `forecast()` | 1024 |
| `forecast_setari()` | 1069 |
| `api_forecast_tara_save()` | 1081 |
| `api_forecast_tara_delete(id)` | 1097 |
| `api_forecast_client_save()` | 1103 |
| `api_forecast_client_toggle(id)` | 1121 |
| `api_forecast_termene_save()` | 1127 |
| `api_forecast_suggest(furnizor)` | 1148 |
| `api_actualizare_date()` | 1160 |
| `api_actualizare_date_status()` | 1198 |
| `api_import_log()` | 1205 |
| `api_upload(tip)` | 1283 |
| `api_upload_status(job_id)` | 1318 |
| `api_forecast_refresh_stoc()` | 1332 |
| `api_forecast_sku_clients(sku)` | 1352 |
| `api_comenzi_drafts()` | 1360 |
| `api_comanda_create()` | 1368 |
| `api_clienti_export_list()` | 1391 |
| `api_clienti_export_add()` | 1404 |
| `api_clienti_export_delete(cod)` | 1439 |
| `api_clienti_search()` | 1450 |
| `api_comanda_get(cid)` | 1466 |
| `api_comanda_update(cid)` | 1474 |
| `api_comanda_delete(cid)` | 1485 |
| `api_comanda_line_add(cid)` | 1491 |
| `api_comanda_line_update(cid, lid)` | 1509 |
| `api_comanda_line_delete(cid, lid)` | 1520 |
| `api_comanda_status(cid)` | 1526 |
| `api_termene_upsert()` | 1551 |
| `export_comanda(cid)` | 1567 |
| `import_comanda_lines(cid)` | 1644 |
| `api_forecast_chat()` | 1676 |
| `api_comanda_avanseaza(comanda_id)` | 2196 |

- [ ] **Step 3: Register in `app/app.py`**

```python
from blueprints.forecast import forecast_bp
app.register_blueprint(forecast_bp)
```

- [ ] **Step 4: Update `url_for` references**

```
grep -rn "url_for(" app/templates/ app/app.py --include="*.html" --include="*.py"
```

The most critical one is the redirect at app.py line 2212 (inside `api_comanda_avanseaza`, which you just moved):

| Old | New |
|-----|-----|
| `url_for('forecast', tab='comenzi')` | `url_for('forecast.forecast', tab='comenzi')` |
| `url_for('forecast')` | `url_for('forecast.forecast')` |
| `url_for('forecast_setari')` | `url_for('forecast.forecast_setari')` |

Update every occurrence in templates and in the just-moved blueprint file.

- [ ] **Step 5: Run the tests**

```
python -m pytest tests/test_flask_routes.py -v
```

Expected: pass. If `test_comenzi_api_list_empty` or `test_clienti_search_empty` fail with 500, there is an import error in the blueprint — check that `_import_job` is referenced via the module variable, not from a deleted global in app.py.

- [ ] **Step 6: Commit**

```bash
git add app/blueprints/forecast.py app/app.py app/templates/
git commit -m "refactor: extract forecast blueprint (forecast, comenzi, upload, actualizare-date)"
```

---

## Task 6 — Extract `reports` blueprint

Routes moved: `produs_detail`, `profitabilitate`, `actualizare`, `export_ppt_dashboard`, `export_ppt_agent`, `export_ppt_client`, `export_ppt_profitabilitate`, `export_excel`, `raportare_basilur`, `raportare_basilur_excel`, `raportare_basilur_ppt`, `export_comanda_intern`, `export_comanda_furnizor`, `export_expirare_view`

**Files:**
- Create: `app/blueprints/reports.py`
- Modify: `app/app.py`, templates

- [ ] **Step 1: Run the tests (baseline)**

```
python -m pytest tests/test_flask_routes.py -v
```

Expected: pass.

- [ ] **Step 2: Create `app/blueprints/reports.py`**

```python
from flask import Blueprint, render_template, request, jsonify, send_file
import queries
import db
import ppt_export
from excel_export import send_excel, timestamped_filename

reports_bp = Blueprint('reports', __name__)
```

Cut and paste from `app/app.py`, changing `@app.route` → `@reports_bp.route`:

| Function | Current line in app.py |
|----------|----------------------|
| `produs_detail(sku)` | 1696 |
| `profitabilitate()` | 1731 |
| `actualizare()` | 1761 |
| `export_ppt_dashboard()` | 1770 |
| `export_ppt_agent()` | 1799 |
| `export_ppt_client()` | 1818 |
| `export_ppt_profitabilitate()` | 1834 |
| `export_excel(report)` | 1848 |
| `raportare_basilur()` | 2000 |
| `raportare_basilur_excel()` | 2049 |
| `raportare_basilur_ppt()` | 2121 |
| `export_comanda_intern(comanda_id)` | 2158 |
| `export_comanda_furnizor(comanda_id)` | 2170 |
| `export_expirare_view()` | 2186 |

- [ ] **Step 3: Register in `app/app.py`**

```python
from blueprints.reports import reports_bp
app.register_blueprint(reports_bp)
```

- [ ] **Step 4: Update `url_for` references**

```
grep -rn "url_for(" app/templates/ app/app.py --include="*.html" --include="*.py"
```

| Old | New |
|-----|-----|
| `url_for('profitabilitate')` | `url_for('reports.profitabilitate')` |
| `url_for('actualizare')` | `url_for('reports.actualizare')` |
| `url_for('produs_detail', ...)` | `url_for('reports.produs_detail', ...)` |
| `url_for('raportare_basilur')` | `url_for('reports.raportare_basilur')` |
| `url_for('export_ppt_dashboard')` | `url_for('reports.export_ppt_dashboard')` |
| `url_for('export_excel', ...)` | `url_for('reports.export_excel', ...)` |

- [ ] **Step 5: Run the full test suite**

```
python -m pytest tests/ -v
```

All test files, not just route tests. Expected: everything green. At this point `app/app.py` contains only: imports, `app = Flask(...)`, config, extension init, blueprint registrations, `before_request`, `healthz`, `teardown_appcontext`, `ensure_cond_resolved`/migrations, `MONTHS_RO`, `RON_USD`, template filters, context processor, error handlers, and `if __name__ == '__main__'`. No route functions remain.

- [ ] **Step 6: Commit**

```bash
git add app/blueprints/reports.py app/app.py app/templates/
git commit -m "refactor: extract reports blueprint (profitabilitate, produs, raportare-basilur, exports)"
```

---

## Task 7 — Introduce `create_app()` factory and `wsgi.py`

All routes are now in blueprints. This task wraps the remaining module-level setup code in a factory function, enabling test isolation and multi-instance usage.

**Files:**
- Modify: `app/app.py` (add factory, keep `app = create_app()` for direct run)
- Modify: `tests/conftest.py` (use `create_app()` instead of importing module-level app)
- Create: `wsgi.py` (at project root, for gunicorn)

- [ ] **Step 1: Run the full test suite (baseline)**

```
python -m pytest tests/ -v
```

Expected: pass.

- [ ] **Step 2: Rewrite `app/app.py` as a factory**

The new `app/app.py` wraps all current module-level code in `create_app(test_config=None)`. The result should be approximately 150 lines. The `if __name__ == '__main__'` block at the bottom creates an app instance for direct execution.

```python
import sys
import os
import datetime
import json
import logging
import logging.handlers
import threading

# Keep sys.path insert at module level so blueprint files can import db, queries, etc.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, redirect, url_for, render_template
from flask_login import current_user
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(_env_path)


def create_app(test_config=None):
    import db
    import queries
    from migrate import apply_migrations
    from blueprints.auth import admin_bp, auth_bp, csrf, login_manager
    from blueprints.analytics import analytics_bp
    from blueprints.bonus import bonus_bp
    from blueprints.pricing import pricing_bp
    from blueprints.forecast import forecast_bp
    from blueprints.reports import reports_bp

    # ── Logging ──────────────────────────────────────────────────────────────
    _log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(_log_dir, exist_ok=True)
    _file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(_log_dir, "app.log"), maxBytes=5 * 1024 * 1024,
        backupCount=3, encoding="utf-8",
    )
    _file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    if not logging.root.handlers:
        logging.root.addHandler(_file_handler)
    logging.root.setLevel(logging.INFO)
    logger = logging.getLogger(__name__)

    # ── Secret key ───────────────────────────────────────────────────────────
    _secret_key = os.environ.get('FLASK_SECRET_KEY', '')
    if not _secret_key or _secret_key == 'change-me-set-FLASK_SECRET_KEY-in-env':
        import warnings
        warnings.warn(
            "FLASK_SECRET_KEY is not set or uses the insecure default. "
            "Set a strong random key in .env before deploying.",
            stacklevel=2,
        )
        _secret_key = 'change-me-set-FLASK_SECRET_KEY-in-env'

    # ── App creation ─────────────────────────────────────────────────────────
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), 'static'),
    )
    app.config.update(
        SECRET_KEY=_secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=False,
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=8),
        REMEMBER_COOKIE_DURATION=datetime.timedelta(days=7),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE='Lax',
        WTF_CSRF_CHECK_DEFAULT=False,
    )
    if test_config:
        app.config.update(test_config)

    # ── Extensions ───────────────────────────────────────────────────────────
    login_manager.init_app(app)
    csrf.init_app(app)
    app.teardown_appcontext(db.close_request_db)

    # ── Blueprints ───────────────────────────────────────────────────────────
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(bonus_bp)
    app.register_blueprint(pricing_bp)
    app.register_blueprint(forecast_bp)
    app.register_blueprint(reports_bp)

    # ── Startup tasks (skipped in test mode) ─────────────────────────────────
    if not app.config.get('TESTING'):
        try:
            queries.ensure_cond_resolved()
        except Exception:
            logger.warning("ensure_cond_resolved failed at startup", exc_info=True)
        with app.app_context():
            apply_migrations()

    # ── Auth gate (before_request) ────────────────────────────────────────────
    @app.before_request
    def _require_auth():
        if request.endpoint in ('static', 'healthz'):
            return
        if request.blueprint == 'auth':
            return
        if not current_user.is_authenticated:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized', 'code': 401}), 401
            return redirect(url_for('auth.login', next=request.full_path))
        if current_user.force_pw_reset and request.endpoint != 'auth.change_password':
            return redirect(url_for('auth.change_password'))

    @app.route('/healthz')
    def healthz():
        return jsonify({'ok': True}), 200

    # ── Template filters ─────────────────────────────────────────────────────
    RON_USD = 4.55

    @app.template_filter('ron')
    def fmt_ron(value):
        if value is None:
            return '—'
        try:
            v = float(value)
            if abs(v) >= 1_000_000:
                return f"{v / 1_000_000:.2f}M RON"
            return f"{int(v):,} RON".replace(',', '.')
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter('usd')
    def fmt_usd(value):
        if value is None:
            return '—'
        try:
            v = float(value) / RON_USD
            if abs(v) >= 1_000_000:
                return f"${v / 1_000_000:.2f}M"
            if abs(v) >= 1_000:
                return f"${v:,.0f}".replace(',', ' ')
            return f"${v:,.0f}"
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter('pct')
    def fmt_pct(value):
        if value is None:
            return '—'
        try:
            return f"{float(value):.1f}%"
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter('delta_class')
    def delta_class(value):
        if value is None:
            return 'text-secondary'
        return 'text-success' if float(value) >= 0 else 'text-danger'

    @app.template_filter('churn_badge')
    def churn_badge(zile):
        if zile is None:
            return '<span class="badge bg-secondary">—</span>'
        z = int(zile)
        if z >= 30:
            return f'<span class="badge bg-danger">{z}z</span>'
        if z >= 16:
            return f'<span class="badge bg-warning text-dark">{z}z</span>'
        return f'<span class="badge bg-success">{z}z</span>'

    @app.template_filter('days_until')
    def days_until(iso_date):
        if not iso_date:
            return None
        try:
            d = datetime.datetime.strptime(str(iso_date)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
        return (d - datetime.date.today()).days

    # ── Context processor ────────────────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        cy = datetime.date.today().year
        return {
            'current_year': cy,
            'today': datetime.date.today(),
            'display_years': [cy - 2, cy - 1, cy],
            'sku_cod_mare': queries.get_sku_cod_mare_map(),
        }

    # ── Error handlers ───────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Forbidden', 'code': 403}), 403
        return render_template('403.html'), 403

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        logger.exception("Unhandled exception on %s %s", request.method, request.path)
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error'}), 500
        return render_template('404.html'), 500

    return app


# Default instance — used by `python app.py` and `flask run`
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
```

- [ ] **Step 3: Update `tests/conftest.py` fixture to use the factory**

Change the `flask_app` fixture (lines 323–327) from:

```python
@pytest.fixture(scope='session')
def flask_app():
    import app as flask_module
    flask_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return flask_module.app
```

To:

```python
@pytest.fixture(scope='session')
def flask_app():
    import app as flask_module          # imports app/app.py (app/ is in sys.path)
    a = flask_module.create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False})
    return a
```

The `client` fixture (lines 330–335) needs no changes.

- [ ] **Step 4: Create `wsgi.py` at the project root**

```python
# wsgi.py — production entry point for gunicorn
# Usage: gunicorn wsgi:app
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app import create_app  # imports app/app.py

app = create_app()
```

- [ ] **Step 5: Run the full test suite**

```
python -m pytest tests/ -v
```

Expected: all tests pass. If the `flask_app` fixture fails, verify `create_app` is exported at the top level of `app/app.py`.

- [ ] **Step 6: Start the server manually and verify the UI**

```
python app/app.py
```

Open `http://127.0.0.1:5000`, log in, and click through: Dashboard, Team, Bonus, Preturi, Forecast, Profitabilitate. Confirm no 500 errors and nav links work.

- [ ] **Step 7: Verify app.py line count**

```
python -c "
with open('app/app.py') as f:
    lines = f.readlines()
print(f'app.py is now {len(lines)} lines (was 2241)')"
```

Expected output: line count under 200.

- [ ] **Step 8: Final commit**

```bash
git add app/app.py tests/conftest.py wsgi.py
git commit -m "refactor: introduce create_app() factory, add wsgi.py — app.py reduced from 2241 to ~180 lines"
```

---

## Self-Review Checklist

- [x] All 6 blueprint files are covered by at least one existing test route
- [x] `_import_job` / `_upload_jobs` globals moved to `forecast.py` (only that module uses them)
- [x] `_log_import` helper uses `paths.DB_PATH` instead of inline path construction
- [x] Template filter and context processor stay in app.py (they depend on `app` instance)
- [x] `ensure_cond_resolved` and `apply_migrations` skipped when `TESTING=True`
- [x] `logging.root.handlers` guard added to prevent duplicate log handlers on repeated `create_app()` calls in tests
- [x] `healthz` endpoint kept in the factory (not in any blueprint) so it has no auth requirement
- [x] `wsgi.py` adds `app/` to sys.path before import to mirror conftest behavior
