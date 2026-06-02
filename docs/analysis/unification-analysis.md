# Unification Analysis — ClaudeTorb + ClaudeTorbStock

**Date:** 2026-05-28
**Decision:** Unified into TorbApp (this directory)

---

## The two apps

### ClaudeTorb
Business intelligence platform for Torb Logistic SRL (FMCG distributor).
- Flask 3, Jinja2, Bootstrap 5, SQLite, Chart.js
- Full auth (Flask-Login, roles, rate limiting, audit log, password reset)
- ~2,241 lines in app.py (being refactored into blueprints as prerequisite)
- 131,898 transaction rows in torb.db
- Features: dashboard, team analytics, client profiles, brand performance, pricing/margin management, commercial conditions, demand forecasting with AutoETS, bonus calculation, AI SQL assistant, PowerPoint/Excel exports

### ClaudeTorbStock
eCommerce operations automation.
- FastAPI (async), vanilla JS (custom dark CSS), SQLite
- No authentication
- Features: eMAG stock sync (live API), Shopify stock sync, eMAG pricing, AI campaign generator, AI content generator
- Working eMAG and Shopify integrations (ClaudeTorb had these as placeholders only)

---

## Keep separate vs. unify

### Keep separate
**Pros:** No migration risk. Each app evolves independently. Simpler codebase per app.
**Cons:** Two logins, two URLs, two deployments. Auth must be built twice (or ClaudeTorbStock stays permanently unauthenticated). Users context-switch between tools. Duplicate infrastructure.

### Unify ✓ (chosen)
**Pros:** Single login. Shared auth covers both. ClaudeTorb's eMAG/Shopify placeholders replaced by ClaudeTorbStock's working implementation. One deployment, one `.env`. Future cross-feature views possible (forecast + live eMAG stock on same screen).
**Cons:** Migration effort. Framework mismatch (Flask vs FastAPI) — resolved by Flask 3's native async support. ClaudeTorb's app.py must be refactored first.

---

## Framework decision: Flask (not FastAPI)

ClaudeTorb is the larger, more mature app. It has auth, a rich BI data model, and an existing test suite. Starting from ClaudeTorb means inheriting all of that for free.

ClaudeTorbStock's async eMAG/Shopify clients work in Flask 3 (which supports `async def` routes via asgiref). The business logic — `EmagClient`, `ShopifyClient`, orchestrators — needs zero changes.

---

## UI decision: Bootstrap 5 shell (ClaudeTorb's)

ClaudeTorb's Bootstrap 5 layout provides the navigation sidebar, breadcrumbs, responsive layout, and auth pages. ClaudeTorbStock's panels are purely client-side JS — they don't depend on the outer shell. Dropping them into a Bootstrap page is a template change only.

The custom dark CSS from ClaudeTorbStock (`.emag-table`, `.stat`, `.badge-*`, `.emag-pagination`, etc.) is preserved and ported to the unified stylesheet. Bootstrap's dark mode applied via `<html data-bs-theme="dark">`.

---

## Auth strategy

ClaudeTorb's `@app.before_request` hook protects all routes automatically. New blueprints from ClaudeTorbStock are protected immediately upon registration — no `@login_required` needed per route. Existing roles (admin/manager/viewer) cover the new features.

When OAuth or SSO is needed later, it plugs into Flask-Login's `user_loader` — no other changes needed.

---

## Database strategy

Two separate SQLite files on the same server:
- `data/torb.db` — ClaudeTorb's rich schema (transactions, forecast, pricing, bonus, users)
- `data/stock.db` — ClaudeTorbStock's lightweight schema (eMAG offers, Shopify sync, campaigns)

Do NOT merge. The schemas serve different domains and have no overlapping tables. Two connection pools (`db.py` and `db_stock.py`) with the same interface.

---

## Concerns and risks

1. **ClaudeTorb's app.py is 2,241 lines.** Must be split into blueprints before adding new features. Plan exists: `docs/plans/01-blueprints-refactor.md`. This is the first prerequisite.

2. **No tests in ClaudeTorb for all routes.** ClaudeTorb has a smoke test suite (`test_flask_routes.py`) that covers all main routes. This is sufficient as a regression guard during the blueprints refactor. More unit tests should be added alongside new features.

3. **ClaudeTorbStock is actively changing.** Several UI improvements were made in the session that produced this document. Stabilize ClaudeTorbStock's UI before porting its frontend to TorbApp.

4. **eMAG credentials mismatch.** ClaudeTorb's `.env.example` had `EMAG_API_KEY` (wrong — the eMAG API uses HTTP Basic Auth). The correct variables are `EMAG_USERNAME` + `EMAG_PASSWORD` from ClaudeTorbStock.

5. **`url_for()` changes.** When routes move to blueprints, every `url_for('function_name')` becomes `url_for('blueprint.function_name')`. All templates must be updated. The blueprints refactor plan includes explicit grep steps for this.

---

## Recommended improvements (before/during unification)

1. **Split ClaudeTorb's app.py first** — non-negotiable prerequisite. Plan is written.
2. **Apply Bootstrap dark theme** to ClaudeTorb now (`<html data-bs-theme="dark">`) to close the visual gap before migration.
3. **Port ClaudeTorbStock's CSS** into ClaudeTorb's `static/css/style.css` — table styles, pagination, toolbar, stat chips.
4. **Add a `db_stock.py`** connection module for ClaudeTorbStock's SQLite tables.
5. **Merge `.env.example`** — unified file with all credentials from both apps (template in `CLAUDE.md`).
6. **Port panel JS** as separate static files per feature (e.g., `static/js/stocuri-emag.js`) rather than one monolithic `app.js`.
