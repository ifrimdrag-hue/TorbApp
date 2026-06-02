# Changelog

All notable changes to this project will be documented in this file.

## [0.4.0] - 2026-05-23

### Authentication
- Added `app/auth.py` — two Flask Blueprints (`/auth`, `/admin`), `User` model (UserMixin), Flask-Login `LoginManager`, Flask-WTF `CSRFProtect`, in-memory rate limiter (10 attempts / 15 min per IP), auth audit log writer, SMTP email sender with graceful degradation
- Login/logout with "Remember me" (8h session, 7d cookie), redirect-back-after-login via `?next=`
- Forced password change flow: `force_pw_reset=1` redirects user to change-password before reaching any other page
- Password reset via email: SHA-256 hashed one-time token, 1h expiry, email enumeration prevention (always shows "sent" message); degrades gracefully when SMTP is not configured
- `require_role(*roles)` decorator for role-based access control; `before_request` guard protects all routes globally — API routes return `401 JSON`, page routes redirect to `/auth/login`
- `app/app.py`: `SECRET_KEY` from env, session/cookie config (`SameSite=Lax`, `HttpOnly`, `Secure=False` for HTTP VPS), `WTF_CSRF_CHECK_DEFAULT=False` (FlaskForm handles CSRF per-form; all existing API routes unchanged)
- `403.html` template and `@app.errorhandler(403)` (JSON for `/api/*`, HTML for pages)

### Admin UI (`/admin`)
- User list with role badges, status, last login
- Create user: generates random temp password displayed once, sets `force_pw_reset=1`
- Edit user: username, email, role, active/inactive toggle
- Admin-initiated password reset: new random temp password displayed once
- Toggle active/inactive (cannot deactivate own account)
- Admin nav item visible only to users with `role='admin'`

### User dropdown in navbar
- Username + role display, change-password link, logout — visible on all authenticated pages
- CSRF meta tag added to `base.html` for future JS use

### Migration `0002_20260523_add_auth`
- Creates `users`, `password_reset_tokens`, `auth_log` tables
- Seeds initial admin: username `admin`, email `vlad.rosioru@gmail.com`, `force_pw_reset=0`

### Dependencies
- Added `flask-login>=0.6`, `flask-wtf>=1.2` to `requirements.txt`
- `.env.example` updated with `FLASK_SECRET_KEY` and `SMTP_*` variables

### Tests
- `tests/conftest.py`: added auth tables to test schema, seeded test admin user, `client` fixture auto-logs in for the session
- All 61 tests pass with authentication enabled

## [0.3.0] - 2026-05-23

### Database migrations
- Introduced versioned migration system: `migrations/` folder at project root
- `migrations/runner.py` — standalone runner; applies pending migrations in `NNNN` order, records each in `schema_version` table; callable as CLI (`python migrations/runner.py [db_path]`) or imported by Flask at startup
- `migrations/0001_20260523_initial.py` — baseline schema (all 20+ tables, views, seed data, status normalisation) converted from the old `apply_migrations()` function
- Naming convention: `NNNN_YYYYMMDD_description.py`
- `schema_version` table tracks applied versions with timestamp; runner is idempotent and safe to run against existing databases
- `app/migrate.py` replaced with a thin wrapper (`apply_migrations()` → `run_all(DB_PATH)`) — `app/app.py` unchanged
- Deployment pipeline now runs `python migrations/runner.py data/torb.db` before `systemctl restart`; a failing migration aborts the deploy and leaves the running service intact

## [0.2.0] - 2026-05-23

### Code quality
- Fixed all 68 ruff linter errors across `app/` and root ETL scripts (E401, E402, E701, E702, E722, E741, F401, F541, F841); re-enabled lint job in CI pipeline

### Project structure
- Reorganized 29 root-level files into logical subdirectories using `git mv` (history preserved)
  - 16 ETL/import scripts → `etl/` (`import_*.py`, `init_*.py`, `rebuild_db.py`, `sync_stoc.py`, `update_data.py`, `merge_client_profi_mega.py`)
  - 13 OS/launcher files → `scripts/` (`start.sh`, `stop.sh`, `restart.sh`, `_torb_server.py`, `launcher.py`, all `.bat`/`.vbs`/`.ps1`)
  - Root now contains only config and documentation files
- Added directory structure rules and routing guide to `CLAUDE.md` (auto-loaded each session)

### Path fixes (required by reorganization)
- `etl/rebuild_db.py`, `etl/update_data.py`: added `sys.path.insert` for sibling dynamic imports
- `scripts/_torb_server.py`: `DIR` now resolves to project root (`dirname(dirname(__file__))`)
- `scripts/start.sh`, `scripts/stop.sh`: `DIR` derives from parent of scripts dir
- `scripts/torb_start.bat`, `torb_actualizeaza.bat`: added `ROOT` variable (parent of `scripts\`); log and script paths updated
- `scripts/ruleaza_import_preturi.bat`, `sync_stoc.bat`: `cd ..` to project root; ETL paths prefixed with `etl\`
- `scripts/setup_task_scheduler.ps1`: `$LogDir` now at project root
- `scripts/launcher.py`: `BASE_DIR` → `dirname(dirname(__file__))` when not frozen
- `app/app.py`: subprocess call updated from `update_data.py` → `etl/update_data.py`

### Testing
- Added `tests/conftest.py`: session-scoped temp SQLite DB with full schema and seed data; patches `DB_PATH` before app import
- Added `tests/test_bonus_calc.py`: 17 unit tests for `payout_multiplier`, `calc_month`, `simulate` (all grid thresholds, gates, penalties)
- Added `tests/test_etl_parsers.py`: 26 tests for ETL parsing functions (`normalize_ref`, `parse_order_date`, `num`, `s`, `extract_romanian_keyword`, `parse_filename_date`)
- Added `tests/test_flask_routes.py`: 9 smoke tests — all main routes return 200, API endpoints return valid JSON, 404 custom page, response shape assertions
- Total: 61 tests pass in CI

### CI/CD
- Test job: pinned to `tests/` directory, removed silent-pass fallback — failures now break the pipeline
- Added `smoke-test-vps` job after deploy: waits 15s, curls all main routes and API endpoints against live VPS, fails pipeline on any non-200
- Added code quality rules and auto-fix hook documentation to `CLAUDE.md` (ruff `--fix --quiet` runs on every `.py` write/edit)

## [0.1.0] - 2026-04-19

### Initial release

**Flask web application** (`app/`)
- Executive dashboard with revenue, agent, and brand KPIs
- Client explorer with drill-down detail pages
- Product/SKU browser
- Team performance view
- Bonus calculator page
- AI natural-language query interface (`/ask`) powered by Claude
- Agentic analytics endpoint (`/agent`)
- SQLite query layer (`queries.py`, 493 lines) with pre-built analytics queries
- Jinja2 templates for all pages with shared base layout and CSS

**Forecast module** (`forecast/`)
- Statistical demand forecasting engine using `statsforecast` (AutoETS/AutoARIMA)
- Brand-level and SKU-level forecast runs with configurable horizon
- Reorder suggestion engine (lead time, safety stock, service-level targets)
- Rolling-origin backtest (3 folds × 13 weeks; WAPE/MASE/bias/service-level metrics)
- Forecast export to Excel
- Brand hierarchy support
- Schema auto-creation on first run
- Flask UI pages: `/forecast` index, brand view, SKU view

**Data pipeline**
- `import_to_sqlite.py` — imports raw Excel transactions into `tranzactii` table (131,898 rows, 2024–2026)
- `import_stoc.py` — flexible stock snapshot importer (flexible column detection)
- `import_tables_extra.py` — imports additional reference tables
- SQLite views: `v_vanzari_an_furnizor`, `v_vanzari_luna_agent`, `v_vanzari_luna_client`, `v_top_sku`, `v_clienti`

**Project documentation**
- `CLAUDE.md` — project context and session instructions for Claude Code
- `STATUS.md` — execution status, delivered phases, open items
- `plan_strategic_5ani.md` — 5-year strategic plan (2026–2030), pillars, financial model
- `torb_background.md` — company background research
- `context/` — business overview, AI opportunities, key risks, data file reference, glossary, memory

**Infrastructure**
- `start.sh` / `stop.sh` / `restart.sh` — server lifecycle scripts with venv auto-detection
- `requirements.txt` — Python dependencies (Flask, pandas, numpy, scipy, statsforecast, openpyxl, anthropic)
- `.gitignore` — excludes venv, compiled Python, SQLite DB, and data files
