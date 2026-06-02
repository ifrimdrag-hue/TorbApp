# TorbApp Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge ClaudeTorb (BI) and ClaudeTorbStock (eCommerce ops) into a single Flask app in this directory, with all features working under ClaudeTorb's auth and Bootstrap 5 UI.

**Architecture:** Copy the refactored ClaudeTorb codebase as the base. Add ClaudeTorbStock's features as new Flask blueprints. Port ClaudeTorbStock's panel JS and CSS into Bootstrap-wrapped templates.

**Tech Stack:** Python 3.9+, Flask 3 + flask[async], Flask-Login, Flask-WTF, Bootstrap 5, SQLite (two files), pytest, httpx (async HTTP for eMAG/Shopify)

**Prerequisites:**
- Phase 1 (blueprints refactor) must be complete in `c:\MINE\ClaudeTorb` before starting Task 1
- Check: `python -m pytest tests/ -v` passes in ClaudeTorb before copying

---

## Task 1 — Bootstrap TorbApp from the refactored ClaudeTorb

**Files:**
- Copy: all of `c:\MINE\ClaudeTorb\` → `c:\MINE\TorbApp\` (excluding `.git`, `data/torb.db`, `__pycache__`)
- Create: `.env.example`
- Create: `requirements.txt` (merged)

- [ ] **Step 1: Verify ClaudeTorb's blueprints refactor is complete**

In `c:\MINE\ClaudeTorb`:
```
python -m pytest tests/ -v
```

Expected: all green. If any test fails, fix it before proceeding.

Also verify `app/app.py` is under 200 lines:
```
python -c "print(sum(1 for _ in open('app/app.py')), 'lines')"
```

- [ ] **Step 2: Copy ClaudeTorb into TorbApp**

From PowerShell (run from `c:\MINE`):
```powershell
$exclude = @('.git', '__pycache__', '*.pyc', 'data\torb.db', '.venv', 'logs')
Copy-Item "ClaudeTorb\*" "TorbApp\" -Recurse -Force -Exclude $exclude
# Copy data directory structure but not the DB
New-Item -ItemType Directory -Force "TorbApp\data" | Out-Null
```

- [ ] **Step 3: Initialize git in TorbApp**

```
cd c:\MINE\TorbApp
git init
git add .
git commit -m "init: seed from refactored ClaudeTorb codebase"
```

- [ ] **Step 4: Verify tests still pass in TorbApp**

```
cd c:\MINE\TorbApp
python -m pytest tests/ -v
```

Expected: all green.

- [ ] **Step 5: Create unified `.env.example`**

```env
# Flask
FLASK_SECRET_KEY=change-me-generate-with-python-secrets-token-hex-32

# Anthropic (AI assistant + campaign/content generation)
ANTHROPIC_API_KEY=sk-ant-...

# eMAG Marketplace API (HTTP Basic Auth — NOT an API key)
EMAG_USERNAME=email@firma.ro
EMAG_PASSWORD=parola_emag

# Shopify
SHOPIFY_SHOP=basilurtea.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxx
SHOPIFY_LOCATION_ID=

# SMTP (password reset emails — optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=email@gmail.com
SMTP_PASSWORD=app_password
SMTP_FROM=Torb App <noreply@torb.ro>
```

Save as `c:\MINE\TorbApp\.env.example`.

- [ ] **Step 6: Update `requirements.txt` — add ClaudeTorbStock dependencies**

Read `c:\MINE\ClaudeTorbStock\requirements.txt` and merge any packages not already in TorbApp's `requirements.txt`. Key additions:
- `httpx` (async HTTP for eMAG/Shopify clients)
- `flask[async]` (enables `async def` route functions in Flask 3)
- Any eMAG/Shopify specific packages

Also add `pytest-asyncio` to `requirements-dev.txt`.

- [ ] **Step 7: Apply Bootstrap dark theme**

In `app/templates/base.html`, find:
```html
<html lang="ro">
```
Change to:
```html
<html lang="ro" data-bs-theme="dark">
```

- [ ] **Step 8: Commit**

```bash
git add .
git commit -m "chore: unify requirements, add dark theme, create .env.example"
```

---

## Task 2 — Add `db_stock.py` — second database connection pool

ClaudeTorbStock features need their own SQLite file (`data/stock.db`). This task creates the connection module that mirrors `db.py`.

**Files:**
- Create: `app/db_stock.py`
- Modify: `app/app.py` (register teardown)
- Modify: `tests/conftest.py` (patch db_stock DB_PATH for tests)

- [ ] **Step 1: Write a failing test**

In `tests/test_db_stock.py`:

```python
def test_db_stock_query_returns_results(client):
    """db_stock.query() works and returns rows (or empty list) from stock.db."""
    import db_stock
    rows = db_stock.query("SELECT 1 AS n")
    assert isinstance(rows, list)
    assert rows[0]['n'] == 1
```

Run:
```
python -m pytest tests/test_db_stock.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'db_stock'`

- [ ] **Step 2: Create `app/db_stock.py`**

```python
"""
Request-scoped SQLite connection pool for stock.db (eMAG/Shopify data).
Mirrors the interface of db.py so blueprint code is consistent.
"""
import os
import sqlite3
from flask import g

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'stock.db'
)


def _new_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _conn():
    if '_stock_db' not in g:
        g._stock_db = _new_connection()
    return g._stock_db


def close_request_db_stock(exc=None):
    db = g.pop('_stock_db', None)
    if db is not None:
        db.close()


def query(sql, params=None):
    cur = _conn().execute(sql, params or [])
    return [dict(r) for r in cur.fetchall()]


def query_one(sql, params=None):
    cur = _conn().execute(sql, params or [])
    row = cur.fetchone()
    return dict(row) if row else None


def get_db():
    return _conn()
```

- [ ] **Step 3: Register teardown in `app/app.py` factory**

Inside `create_app()`, after `app.teardown_appcontext(db.close_request_db)`:

```python
from db_stock import close_request_db_stock
app.teardown_appcontext(close_request_db_stock)
```

- [ ] **Step 4: Update `tests/conftest.py` to patch db_stock path**

After the existing `_db_mod.DB_PATH = _TEST_DB` line, add:

```python
import db_stock as _db_stock_mod  # noqa: E402
# Use same temp DB for stock tables in tests (simpler than two separate files)
_db_stock_mod.DB_PATH = _TEST_DB
```

- [ ] **Step 5: Run the test**

```
python -m pytest tests/test_db_stock.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/db_stock.py app/app.py tests/conftest.py tests/test_db_stock.py
git commit -m "feat: add db_stock.py — second SQLite connection pool for stock.db"
```

---

## Task 3 — Port eMAG stock blueprint

Ports ClaudeTorbStock's eMAG preview + sync to a Flask blueprint. The async orchestrators are copied unchanged; only the route layer is new.

**Files:**
- Copy: `c:\MINE\ClaudeTorbStock\backend\automations\stocuri_emag\` → `app\automations\stocuri_emag\`
- Create: `app/blueprints/stocuri_emag.py`
- Modify: `app/app.py` (register blueprint)
- Modify: `tests/conftest.py` (add stock schema tables)

- [ ] **Step 1: Write the failing test**

In `tests/test_blueprint_stocuri_emag.py`:

```python
import json
from unittest.mock import AsyncMock, patch


def test_emag_preview_no_report_returns_200(client):
    """POST /api/stocuri/emag/preview with no file returns has_report=false."""
    fake_result = {
        'rows': [],
        'skus_not_in_emag': [],
        'warnings': [],
        'summary': {'total_emag_offers': 0, 'no_ean': 0},
        'has_report': False,
    }
    with patch(
        'blueprints.stocuri_emag.preview_emag_only',
        new=AsyncMock(return_value=type('R', (), fake_result)())
    ):
        resp = client.post('/api/stocuri/emag/preview')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['has_report'] is False


def test_emag_preview_page_loads(client):
    resp = client.get('/stocuri/emag')
    assert resp.status_code == 200
    assert b'<!DOCTYPE' in resp.data or b'<html' in resp.data
```

Run:
```
python -m pytest tests/test_blueprint_stocuri_emag.py -v
```

Expected: FAIL with 404 (routes not registered yet).

- [ ] **Step 2: Copy the eMAG automations**

```powershell
New-Item -ItemType Directory -Force "app\automations\stocuri_emag" | Out-Null
Copy-Item "c:\MINE\ClaudeTorbStock\backend\automations\stocuri_emag\*" "app\automations\stocuri_emag\" -Recurse
New-Item -ItemType File -Force "app\automations\__init__.py" | Out-Null
New-Item -ItemType File -Force "app\automations\stocuri_emag\__init__.py" | Out-Null
```

- [ ] **Step 3: Create `app/blueprints/stocuri_emag.py`**

```python
import asyncio
from flask import Blueprint, render_template, request, jsonify
from automations.stocuri_emag.orchestrator import emag_preview, preview_emag_only

stocuri_emag_bp = Blueprint('stocuri_emag', __name__)


@stocuri_emag_bp.route('/stocuri/emag')
def stocuri_emag_page():
    return render_template('stocuri/emag.html')


@stocuri_emag_bp.route('/api/stocuri/emag/preview', methods=['POST'])
async def api_emag_preview():
    raport = request.files.get('raport')
    if raport:
        result = await emag_preview(raport)
    else:
        result = await preview_emag_only()
    return jsonify({
        'rows': [r._asdict() for r in result.rows],
        'skus_not_in_emag': result.skus_not_in_emag,
        'warnings': result.warnings,
        'summary': result.summary,
        'has_report': result.has_report,
    })


@stocuri_emag_bp.route('/api/stocuri/emag/sync', methods=['POST'])
async def api_emag_sync():
    from automations.stocuri_emag.orchestrator import emag_sync
    data = request.get_json(force=True)
    rows_to_update = data.get('rows', [])
    result = await emag_sync(rows_to_update)
    return jsonify(result)
```

- [ ] **Step 4: Create the template `app/templates/stocuri/emag.html`**

```html
{% extends "base.html" %}
{% block title %}Stoc eMAG{% endblock %}
{% block content %}
<div class="container-fluid px-4">
  <!-- Panel HTML from ClaudeTorbStock/frontend/index.html
       Copy the <section data-panel="stocuri/emag"> content here,
       removing the outer <section> wrapper since base.html provides the layout. -->
</div>
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='js/stocuri-emag.js') }}"></script>
{% endblock %}
```

Extract the eMAG panel JS from `c:\MINE\ClaudeTorbStock\frontend\app.js` into `app/static/js/stocuri-emag.js`. Update all `fetch('/api/stocuri/emag/...')` calls — the URLs stay the same (same prefix).

- [ ] **Step 5: Register the blueprint in `app/app.py`**

```python
from blueprints.stocuri_emag import stocuri_emag_bp
app.register_blueprint(stocuri_emag_bp)
```

Also add `stocuri_emag` to the sidebar in `app/templates/base.html`:
```html
<li class="nav-item">
  <a class="nav-link" href="{{ url_for('stocuri_emag.stocuri_emag_page') }}">
    <i class="bi bi-box-seam"></i> Stoc eMAG
  </a>
</li>
```

- [ ] **Step 6: Run the tests**

```
python -m pytest tests/test_blueprint_stocuri_emag.py tests/test_flask_routes.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add app/automations/ app/blueprints/stocuri_emag.py app/templates/stocuri/ \
        app/static/js/stocuri-emag.js app/app.py app/templates/base.html \
        tests/test_blueprint_stocuri_emag.py
git commit -m "feat: add stocuri_emag blueprint (eMAG stock preview + sync)"
```

---

## Task 4 — Port Shopify stock blueprint

Mirrors Task 3 for ClaudeTorbStock's Shopify sync feature.

**Files:**
- Copy: `c:\MINE\ClaudeTorbStock\backend\automations\stocuri_shopify\` → `app\automations\stocuri_shopify\`
- Create: `app/blueprints/stocuri_shopify.py`
- Create: `app/templates/stocuri/shopify.html`
- Create: `app/static/js/stocuri-shopify.js`
- Modify: `app/app.py`, `app/templates/base.html`

Follow the exact same pattern as Task 3. The blueprint name is `stocuri_shopify`, route prefix is `/stocuri/shopify`, API prefix is `/api/stocuri/shopify`.

Test file: `tests/test_blueprint_stocuri_shopify.py` — check `/stocuri/shopify` returns 200.

---

## Task 5 — Port campaigns blueprint

**Files:**
- Copy: `c:\MINE\ClaudeTorbStock\backend\automations\campanii\` → `app\automations\campanii\`
- Create: `app/blueprints/campanii.py`
- Create: `app/templates/campanii/index.html`
- Create: `app/static/js/campanii.js`
- Modify: `app/app.py`, `app/templates/base.html`

Follow the Task 3 pattern. Blueprint name: `campanii`. Route prefix: `/campanii`.

---

## Task 6 — Port content generation blueprint

**Files:**
- Copy: `c:\MINE\ClaudeTorbStock\backend\automations\continut\` → `app\automations\continut\`
- Create: `app/blueprints/continut.py`
- Create: `app/templates/continut/index.html`
- Create: `app/static/js/continut.js`
- Modify: `app/app.py`, `app/templates/base.html`

Follow the Task 3 pattern. Blueprint name: `continut`. Route prefix: `/continut`.

---

## Task 7 — Port ClaudeTorbStock CSS into unified stylesheet

ClaudeTorbStock's `frontend/style.css` contains panel-specific styles that need to live in TorbApp. Rather than including the whole file, extract only the custom component classes.

**Files:**
- Modify: `app/static/css/style.css`

- [ ] **Step 1: Identify custom classes to port**

From `c:\MINE\ClaudeTorbStock\frontend\style.css`, extract all rule blocks for:
- `.emag-table`, `.emag-table-wrap`, `.emag-row`, `.emag-name`, `.emag-row--*` — table styles
- `.emag-pagination`, `.emag-pagination-info` — pagination bar
- `.emag-toolbar`, `.emag-filter-label` — filter toolbar
- `.emag-summary-inline`, `.emag-summary-warn` — compact summary
- `#emagTable thead th[data-sort]`, `.sort-asc`, `.sort-desc` — sortable headers
- `.table--emag-only th/td:first-child/:last-child` — column hiding
- `.stat`, `.stat .label`, `.stat .value`, `.stat.success/warning/muted/accent` — stat cards
- `.badge-*` — status badges
- `.dropzone`, `.dz-*` — file upload dropzone
- `.conn-dot`, `.conn-dot--*` — connection status indicator

- [ ] **Step 2: Append to `app/static/css/style.css`**

Add a section header `/* ── ClaudeTorbStock components ── */` then paste the extracted rules.

Adjust any hardcoded colors that clash with Bootstrap dark theme (replace pure blacks/whites with CSS variables like `var(--bs-body-bg)`).

- [ ] **Step 3: Commit**

```bash
git add app/static/css/style.css
git commit -m "style: port ClaudeTorbStock component CSS into unified stylesheet"
```

---

## Task 8 — eMAG pricing blueprint (optional)

If ClaudeTorbStock has a working `preturi_emag` automation, port it using the same blueprint pattern as Task 3.

---

## Task 9 — Deployment config

**Files:**
- Create: `deploy/nginx.conf`
- Create: `deploy/torb-app.service` (systemd)
- Modify: `wsgi.py` if needed

- [ ] **Step 1: Create `deploy/nginx.conf`**

```nginx
server {
    listen 80;
    server_name hub.robrands.ro;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name hub.robrands.ro;

    ssl_certificate     /etc/letsencrypt/live/hub.robrands.ro/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/hub.robrands.ro/privkey.pem;

    location /static/ {
        alias /opt/torbapp/app/static/;
        expires 1d;
    }

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

- [ ] **Step 2: Create `deploy/torb-app.service`**

```ini
[Unit]
Description=TorbApp — Torb Logistic unified operations hub
After=network.target

[Service]
Type=notify
User=torbapp
WorkingDirectory=/opt/torbapp
EnvironmentFile=/opt/torbapp/.env
ExecStart=/opt/torbapp/.venv/bin/gunicorn \
    --workers 2 \
    --bind 127.0.0.1:8080 \
    --timeout 120 \
    --access-logfile /var/log/torbapp/access.log \
    wsgi:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Commit**

```bash
git add deploy/
git commit -m "deploy: add nginx config and systemd service for VPS deployment"
```

---

## Checklist before declaring done

- [ ] `python -m pytest tests/ -v` — all green
- [ ] All ClaudeTorb features work: dashboard, team, bonus, preturi, forecast, AI ask
- [ ] eMAG stock preview loads (no file → eMAG-only mode, with file → comparison mode)
- [ ] eMAG sync works end-to-end
- [ ] Shopify sync works end-to-end
- [ ] Campaign generator works
- [ ] Auth: login, logout, change password, admin user management
- [ ] Dark Bootstrap theme looks consistent across all panels
- [ ] Sidebar nav links all work
- [ ] No 500 errors in any route
