# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Forecast: spec-completion engine pieces (neutral months, INACTIV, DELISTAT, MOQ floor) (2026-07-04)

Low-risk, fully-specified parts of the owner spec/brief, all pure + unit-tested and wired only into the `?model=nou` path (default stays legacy — validate via `?compare=1` before flipping).

- **Neutral months (Brief §4.1, level 1)** — `pair_engine.neutral_months`: a month where ≥ `prag_neutru_multi_client`% (default 70) of an article's covering clients sold zero is treated as a supply-gap and excluded from every pair's mean (distinguishes "nobody could buy" from "demand fell"). Requires ≥2 covering clients so single-client churn can't trip it.
- **Global INACTIV cut (Spec §7)** — `pair_engine.is_inactive`: zero total sales across the last `taiere_inactiv_luni` (6) closed months → article forecast 0; neutral months don't count as evidence, and strongly seasonal articles (peak seasonal index ≥ 3.0) are never auto-inactivated.
- **DELISTAT label (Spec §5.2)** — `delisting_status` gains `confirm_days`: a SUSPECT pair auto-labels DELISTAT past `prag + confirmare_delistare_zile` (90). Same numeric effect as SUSPECT (contribution 0) — label only, for reporting (`n_delistat`).
- **MOQ floor (Spec §8)** — `forecast_logic.split_with_safety(..., moq=None)` applies `max(brut, MOQ)` before bax rounding, never lifting a zero need into an order. Inert until MOQ data exists (`produse` has no MOQ column).
- **Daily stock-snapshot capture** — new `etl/snapshot_stoc.py` copies the latest `stoc` snapshot into `stock_snapshot` (idempotent per date) so OOS history accrues for level-2 later. `stock_snapshot` survives the partial rebuild; open item is wiring the run into `rebuild_db.main()` / a scheduled job.
- Config: migration `0018` seeds `prag_neutru_multi_client` (70). Owner decisions cross-referenced in `app/templates/decision_torb.html` (1–10 resolved by the docs; 6/9/11–14 open). Plan + spec digest: `docs/plans/2026-07-04-forecast-spec-completion.md`. Tests: `tests/test_pair_engine.py`, `test_forecast_reorder.py` (+8).

### Forecast: client × article demand model, behind a toggle (2026-07-04)

- New `app/forecast/pair_engine.py` computes demand per `(client, article)` pair instead of averaging a SKU across all clients: adaptive per-pair window (first sale → 36 months), monthly mean with zero-filled no-sale months (declining pairs decay to 0), article-level seasonal index gated at ≥24 months of history and clamped to `[0.2, 5.0]`, and an adaptive delisting `SUSPECT` flag when a pair's gap since last purchase exceeds `max(180 days, 3× its mean order interval)` (its contribution then drops to 0). Directly addresses backlog **B4** (delisted/declining SKUs kept being reordered).
- Order formula (partial): `forecast_logic.split_with_safety` adds `safety = coef × monthly forecast` (default 0.25) and rounds up to the supplier bax (`produse.buc_cutie`); MOQ floor deferred (`app/templates/decision_torb.html` item 6).
- Tunable parameters in a new `forecast_config` table (migration `0017`) + `app/forecast/config.py`, edited on a "Parametri forecast" card at `/forecast/setari`.
- Wired behind `?model=nou` in `build_suggestion` (Suggest tab) and `forecast_stoc_extended` (Stoc tab); the default `?model=actual` path is unchanged. `?compare=1` shows both models side by side (Δ columns) for owner validation before the default flips. UI: model toggle, "Suspect delistare" badge, seasonality "fără ajustare (<24 luni)" marker, suggestion-breakdown popover.
- Deferred spec items (§4.4 out-of-stock months, §5 full DELISTAT/REACTIVAT lifecycle, §6 new-listing ramp-up, §8 MOQ, §10 recompute cadence) await owner decisions — `app/templates/decision_torb.html` items 5–10.
- Spec: `docs/Specificatie Forecast Torb.docx`. Documented in `app/forecast/README.md`, `docs/BUSINESS_LOGIC.md` §7.1, `docs/TECHNICAL.md` §Data. Tests: `tests/test_pair_engine.py`, `test_forecast_reorder.py`, `test_forecast_config.py`, `test_forecast_routes.py`.

### Central logging config — rotating app + error logs, quieter werkzeug (2026-07-04)

- New `app/logging_config.py` (`setup_logging()`, idempotent) attaches two rotating file handlers to the root logger: `logs/app.log` (all levels per `LOG_LEVEL`, default INFO; 2 MB × 5) and `logs/errors.log` (ERROR-only; 1 MB × 3). `create_app()` routes through it.
- Noisy third-party loggers (`werkzeug`, `httpx`, `urllib3`) raised to WARNING so `app.log` isn't flooded with per-request `200 -` access lines; genuine 4xx/5xx still surface. Console echo only when `FLASK_DEBUG` is set.
- Documented in `docs/TECHNICAL.md` §Application logging.

### Forecast page — velocity-basis toggle aligning screen ↔ Excel (2026-07-03)

- `/forecast` Stoc tab: a `3 ani / 90 zile` segmented toggle next to Export switches the basis for the displayed `Vânz./lună` + `Zile stoc` columns (urgency badge + sort follow from `Zile stoc`); `Sug. RO/HU` stay on the seasonal model. Excel export now runs off the same `forecast_stoc_extended(vel=)` data as the page (and honours the search filter), so screen and Excel match for the selected mode. Default `3 ani` (prior behaviour). Resolves the page-vs-Excel velocity divergence as a runtime choice.

### Forecast page — order-status vocabulary, FK cascade, re-importable export (2026-07-03)

- Order-status vocabulary normalised (migration `0016`): legacy capitalised statuses folded (`Emisa`/`Confirmata`→`confirmata`, `In tranzit`→`in_tranzit`, `Receptionata`→`livrata`); `comanda_update` rejects an empty/whitespace status (still applies other fields) so the modal can't write `status=''`; all transit `IN(...)` lists standardised to `('confirmata','in_tranzit')`.
- `PRAGMA foreign_keys=ON` on app connections so `ON DELETE CASCADE` works (deleting an order removes its lines instead of orphaning them).
- New `— Cantitate comandată` column in the order Excel export so the export → edit → re-import round-trip works.
- Removed dead `forecast_stoc()`; extracted the shared `_ro_hu_split()` used by `build_suggestion` + `forecast_stoc_extended` (numerically identical before/after). Tests: `test_order_status.py`, `test_comanda_excel_roundtrip.py`, `test_ro_hu_split.py`.

### Forecast page — 10 P0/P1 fixes (2026-07-03)

- Restored the dead Export HU split (`clienti_export.cod_client` `BRANDMIX`→`1429`, `HUNTRADE`→`1430`, + validation when adding a client code); KPI cards count distinct SKUs not lots; `Zile stoc` excludes in-transit stock; transit ETA prefers `costuri_landing.eta`; export-code query made SQL-injection-safe; `_listing_changes()` keys normalised to match `build_suggestion()`; "Confirmă Comanda" excludes filter-hidden rows; `escapeHtml()` applied across client-side HTML building; removed dead `/api/comenzi/<id>/avanseaza`. Plan: `docs/plans/2026-07-03-forecast-p0-p1-fixes.md`. Tests: `test_forecast_queries.py` + 3 in `test_flask_routes.py`.

### Leonex order import — map supplier codes to Cod TORB (2026-07-03)

- New `corr_leonex_cod_mapping` table (migration 0014, mirrored in `etl/rebuild_db.py`) mapping Leonex supplier codes (`MK…`) to Torb internal codes (`cod_mare`), seeded with 10 pairs
- `etl/import_comenzi_tranzit_leonex.py` now resolves `MK → cod_torb → stoc.sku` and stores each order line under the Torb identity, so in-transit orders merge into the correct product row in the stock/orders view instead of surfacing as stray MK-coded rows
- Unmapped codes are skipped and reported (`AVERTISMENT:` line → amber note in the upload UI); upload job surfaces the warning via a new `avertisment` field
- Documented in `docs/BUSINESS_LOGIC.md` §8 and `docs/TECHNICAL.md` §Data

### Documentation reorganization (2026-07-02)

- Consolidated all project documentation into four category files under `docs/`:
  - `docs/BUSINESS.md` — company profile, market research, risks, AI opportunities, and the full 2026–2030 strategic plan (absorbs `context/` torb_background, project_business_overview, key_facts, project_key_risks, project_ai_opportunities, ai_optimization_report_1, glossary business sections, plan_strategic_5ani)
  - `docs/BUSINESS_LOGIC.md` — domain vocabulary, data model, transaction anatomy, bonus calculation, virtual brands, stock sync, forecast pointers (absorbs `context/glossary.md` data sections + `.claude/project_knowledge.md` feature sections)
  - `docs/TECHNICAL.md` — data layer, input-file map, deploy pipeline, VPS infrastructure, Romanian encoding rules, Typst manual rules (absorbs `.claude/project_knowledge.md` + `context/infrastructure.md` + `context/reference_data_files.md`)
  - `docs/BACKLOG.md` — tech-debt, infrastructure pending items, forecast audit findings, product/AI opportunity backlog
- `context/infrastructure_history.md` → `docs/TECHNICAL_history.md` (write-mostly archive, unchanged)
- `context/` now holds only the live `STATUS.md`; `.claude/project_knowledge.md` deleted (content redistributed)
- `CLAUDE.md` routing table updated to the new layout; working preferences consolidated from Claude session memory
- Path references updated in `README.md`, `.env.example`, `etl/backup_db.py`, `app/app.py`, `context/STATUS.md`
- Stale status fixed: bonus module marked delivered (was still listed as blocked), margin-audit deadline marked overdue
- Compiled manual PDFs moved from `docs/` root to `docs/manuals/*.pdf` (flat); Typst sources remain in gitignored per-manual subfolders — compile convention updated in `docs/TECHNICAL.md` §Typst
- `docs/superpowers/` dissolved: plans → `docs/plans/`, specs → `docs/specs/` (still gitignored); AI-workflow outputs now go directly under `docs/` (rule added to `CLAUDE.md`)

### Business constants centralised + true Torb cost on Auchan sales (2026-07-02)

- New `app/business_constants.py` (Auchan/Tobra exception: agent, client codes, invoice prefix, 30-day cost window), used by `import_vanzari_erp.py` + `import_vanzari_tobra_auchan.py`. New `corr_vanzari_tobra` table (migration 0013): Torb→Tobra lines (code 719) are diverted there at ERP import instead of dropped. The Auchan import overrides `pret_cumparare` with the 30-day simple mean per `cod_produs` at each row's date and recomputes `val_achizitie`/`marja_bruta`. Load order: ERP sales before Auchan sales.

### Forecast page audit — analysis only (2026-07-02)

- `docs/analysis/forecast_page_analysis.md`: architecture of the 5 tabs + AI agent, both suggestion algorithms, a column-by-column Stoc-tab reference, the full API, and 20 ranked issues — fed the P0/P1 and second-wave fix batches above.

### Organsia — fourth Basilur virtual brand (2026-07-01)

- `B.ECO ORGANSIA*` (ERP) / `ORGANSIA - …` (price list) products, previously mislabelled `Basilur`, get a prefix-derivation rule in the three ETL modules + a `produse` override in `import_preturi.py`, plus a 120-day lead-time seed (migration `0012`) with historical backfill (~20 stock, ~718 transactions, 11 products). Organsia now appears as the fourth brand in the Basilur report (Excel + PPT, colour `#6f42c1`), the bonus/post dropdowns, and AI prompts. Virtual-brand logic in `docs/BUSINESS_LOGIC.md`. Test: `test_derive_furnizor.py`.

### Monthly bonus engine redesign (2026-06-16)

- Config-driven bonus module (`feat/bonus-redesign`): per-agent monthly targets (sales, margin, 9 individual ranges, client count, new-clients-per-range, collections, scriptic), configurable weights + bonus value, a payout grid with thresholds (80% gate), a default +20% vs the same month last year, a month-close flow with a frozen snapshot, and agent management from the UI. Tables `bonus_config`, `bonus_lunar_config`, `bonus_obiective_strategice`, `bonus_payout_grid`, `bonus_istoric` (migration 0011). Pages: `/bonus`, `/bonus/obiective`, `/bonus/inchidere`, `/bonus/config`, `/bonus/clienti-noi-gama`.

### Database backup & restore — production (2026-06-11)

- `app/backup_db.py` (SQLite online-backup API, gzip, retention 15 days / min 3) + CLI `etl/backup_db.py` (backup/list/restore). Trigger: daily cron 02:30 on the prod VPS + automatic pre-deploy backup in CI before migrations. Admin page `/admin/db`: list, manual backup, download, restore with a typed "RESTORE" confirmation (auto safety backup + re-apply migrations). `PRAGMA busy_timeout=5000` added to `app/db.py`.

### Connection status served from server-side cache (2026-06-11)

- `connection_status` table (migration 0010) + `app/connection_cache.py` (3-min TTL) — at most one external eMAG/Shopify API call per platform per window, shared across all users. `connection-test` routes unchanged in URL/shape (new fields `cached`, `checked_at`); the connDot tooltip shows the check time.

## [0.6.0] - 2026-06-10

### Stock sync — history and eMAG sync

- Added unified sync history for both platforms: `shopify_sync_sessions` + `shopify_sync_rows` tables (migration 0006), then `platform` column added (migration 0007) — single table pair tracks sessions for both eMAG and Shopify
- Sync history panel on `/stocuri` shows last 10 sessions per platform (date + filename); clicking a session and pressing *Incarca date istorice* loads a read-only historical view of that sync
- eMAG sync history endpoints: `GET /api/stocuri/emag/sync-history` and `GET /api/stocuri/emag/sync-history/<id>`
- eMAG sync now persists session + row results identically to Shopify
- User audit on stock syncs: `sync_sessions.user_id` (migration 0008) records who ran each eMAG/Shopify sync (shown in the `/stocuri` history); tables renamed `shopify_sync_*` → `sync_sessions`/`sync_rows` (migration 0009, prefix obsolete now that sync is multi-platform)
- Shopify stock sync integration (GraphQL Admin API 2025-04, OAuth client credentials); unified `/stocuri` page with an eMAG/Shopify radio switch (delivered 2026-06-03)

### Project structure

- Moved `docs/plan_strategic_5ani.md`, `docs/STATUS.md`, `docs/torb_background.md` → `context/` (git history preserved via `git mv`); `docs/` now holds only implementation plans, analysis, specs, and user manuals
- Updated all path references in `CLAUDE.md`, `README.md`, `context/STATUS.md`
- Added `docs/manuals/` for end-user documentation (Typst source + compiled PDF); `.gitignore` updated to version only `.pdf` files from that tree

### Documentation

- Added `docs/manuals/stock/manual_stoc.typ` — Romanian user manual for the Sincronizare Stoc feature (eMAG + Shopify); compiled to `manual_stoc.pdf`

### Fixes

- `README.md`: corrected eMAG API version (v3 → v4.5.1), updated test count (66 → 73)

## [0.5.0] - 2026-06-04

### Technical Debt — Phases 1, 2, 3

- Deleted `etl/init_forecast_tables.py` (dead code — broken DB path, schema superseded by migrations 0001 + 0004)
- Updated default AI model in `app/config.py` from retired `claude-opus-4-7` to `claude-sonnet-4-6`
- CI/CD: added explicit `python migrations/runner.py data/torb.db` step before `systemctl restart` — failed migrations now abort deploy rather than crashing the running app
- Tests: replaced 289-line hand-maintained schema in `tests/conftest.py` with `migrations.runner.run_all()` — test schema is always in sync with production schema automatically
- Refactored `app/queries.py` (3,236 lines) into `app/queries/` package with 9 domain modules (`_shared`, `analytics`, `clients`, `products`, `pricing`, `orders`, `forecast`, `bonus`, `export`); `__init__.py` re-exports all names — zero callsite changes required
- DB cleanup (earlier in session): deleted orphan `clienti_export_old` table (migration 0005), moved forecast tables to migration 0004, removed dead `db_stock.py` + `data/stock.db`
- Documentation: corrected `CLAUDE.md` file paths (STATUS.md, plan_strategic_5ani.md moved to `docs/`), updated `README.md` test count, refreshed `docs/STATUS.md` (45 days stale), updated `context/project_ai_opportunities.md` (Shopify delivered)

### Comprehensive code audit (2026-05-28)

- Four parallel audit agents (backend, frontend, infrastructure, AI modules). Applied: env-controlled `SESSION_COOKIE_SECURE` + `LOG_LEVEL`, a 500 error handler, auth-gate fix for blueprint statics, open-redirect mitigation, `import_stoc.py` path fix, 10 MB upload check, dynamic filenames in the orchestrator, `BadRequestError`/`APIStatusError` handling in `ai_suggestions`, JSON error logging in the campaign/auto-post generators, light theme with dark sidebar, collapsible nav (localStorage), Trendyol packages template.

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
