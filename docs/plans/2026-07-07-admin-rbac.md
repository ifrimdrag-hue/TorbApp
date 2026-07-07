# Admin RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the Admin module into three tabs (Utilizatori, Mentenanță DB, Autorizări), add DB-backed dynamic roles, and gate every nav link + its routes by an editable role→nav authorization matrix.

**Architecture:** A canonical `app/nav_registry.py` is the single source of truth for nav links. `app/authz.py` resolves, per role, which nav keys are granted (deny-by-default; `admin` is a hardcoded superuser) and maps each Flask endpoint to a nav key. `base.html` renders the sidebar from the registry filtered by grants; the app's `before_request` returns 403 for a denied endpoint. Roles + grants live in new `adm_roles` / `adm_role_nav` tables; `users` is renamed to `adm_users`.

**Tech Stack:** Flask, Flask-Login, Flask-WTF, SQLite, Jinja2, Bootstrap 5, pytest.

**Execution order (dependency-safe — overrides the numeric order):** 3 → 1 → 2 → 4 → 5 → 6 → 7 → 9 → 10 → 8 → 11. This puts `nav_registry` (Task 3) before the migration seed (Task 1) and the Autorizări route (Task 10) before the admin tab bar (Task 8), so no task references something that does not yet exist.

## Global Constraints

- **English** for code/comments/commits; **Romanian** for all UI text and user-facing strings.
- All Python must pass `ruff check .` (a PostToolUse hook auto-fixes on write). Forbidden: E401/E402/E701/E702/E722/E741/F401/F841.
- Romanian strings in `.py` files: read `docs/TECHNICAL.md §Encoding` before editing any `.py` containing Romanian (source files use a specific encoding convention — do not corrupt existing mojibake headers).
- Migrations: file `migrations/NNNN_YYYYMMDD_desc.py` exporting `VERSION:int`, `NAME:str`, `up(conn)`. **`up()` must NOT call `conn.commit()`** (runner commits). Next free number is **0037**.
- New files obey the layout in `CLAUDE.md`: Flask code → `app/`, tests → `tests/`, migrations → `migrations/`. No `.py` in repo root.
- Frontend errors surface via the shared `AppError.show()` modal (`app/static/js/app-error.js`), never ad-hoc inline text.
- `admin` role = superuser: always full nav + route access, never appears as a matrix column, cannot be locked out.
- Deny-by-default: no `adm_role_nav` row = link hidden + route 403 for that non-admin role.

---

### Task 1: Migration 0037 — tables, rename, seed

**Files:**
- Create: `migrations/0037_20260707_admin_rbac.py`
- Test: `tests/test_admin_rbac_migration.py`

**Interfaces:**
- Produces: tables `adm_roles(id,name,label,is_system,created_at)`, `adm_role_nav(role_id,nav_key)`, and renames `users`→`adm_users`. Seeds roles `admin/manager/viewer` (`is_system=1`) and grants every nav key to `manager`+`viewer`.
- Consumes: `nav_registry.NAV_REGISTRY` (Task 3) for the seed key list. **Task 3 must be authored before this migration's seed step**, but the migration file can be written first with the import; if executing strictly in order, implement Task 3's `nav_registry.py` first, then return here. (Subagent note: do Task 3 before running Task 1's tests.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_rbac_migration.py
import sqlite3
import importlib.util
from pathlib import Path

MIG = Path(__file__).resolve().parents[1] / "migrations" / "0037_20260707_admin_rbac.py"


def _load():
    spec = importlib.util.spec_from_file_location("mig0037", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _base_db(path):
    """Minimal pre-0037 schema: a users table like migration 0002 leaves."""
    c = sqlite3.connect(path)
    c.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY, username TEXT, email TEXT,
            password_hash TEXT, role TEXT, is_active INTEGER DEFAULT 1,
            force_pw_reset INTEGER DEFAULT 0, last_login_at TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE auth_log (id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id), event TEXT);
        """
    )
    c.commit()
    return c


def test_migration_creates_tables_renames_and_seeds(tmp_path):
    db = str(tmp_path / "t.db")
    conn = _base_db(db)
    mod = _load()
    mod.up(conn)
    conn.commit()

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "adm_users" in tables and "users" not in tables
    assert "adm_roles" in tables and "adm_role_nav" in tables

    roles = dict(conn.execute("SELECT name, is_system FROM adm_roles").fetchall())
    assert roles == {"admin": 1, "manager": 1, "viewer": 1}

    from importlib import import_module
    import sys
    sys.path.insert(0, str(MIG.resolve().parents[1] / "app"))
    reg = import_module("nav_registry")
    all_keys = {i.key for i in reg.NAV_REGISTRY}
    for role in ("manager", "viewer"):
        rid = conn.execute("SELECT id FROM adm_roles WHERE name=?", (role,)).fetchone()[0]
        granted = {r[0] for r in conn.execute(
            "SELECT nav_key FROM adm_role_nav WHERE role_id=?", (rid,))}
        assert granted == all_keys, f"{role} should be seeded with every nav key"
    # admin gets no rows (bypassed)
    aid = conn.execute("SELECT id FROM adm_roles WHERE name='admin'").fetchone()[0]
    assert conn.execute(
        "SELECT COUNT(*) FROM adm_role_nav WHERE role_id=?", (aid,)).fetchone()[0] == 0


def test_migration_is_idempotent(tmp_path):
    db = str(tmp_path / "t.db")
    conn = _base_db(db)
    mod = _load()
    mod.up(conn); conn.commit()
    mod.up(conn); conn.commit()  # second run must not raise
    assert conn.execute("SELECT COUNT(*) FROM adm_roles").fetchone()[0] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_admin_rbac_migration.py -v`
Expected: FAIL — migration file does not exist.

- [ ] **Step 3: Write the migration**

```python
# migrations/0037_20260707_admin_rbac.py
"""Migration 0037 — Admin RBAC: dynamic roles + nav authorization.

Creates adm_roles + adm_role_nav, renames users -> adm_users (SQLite >=3.25
auto-rewrites child FK references), seeds the three system roles, and grants
every current nav key to manager + viewer so day-one behavior is unchanged.
admin is a superuser and intentionally receives no grant rows.
"""
import os
import sys

VERSION = 37
NAME = "0037_20260707_admin_rbac"


def _nav_keys():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app"))
    from nav_registry import NAV_REGISTRY
    return [item.key for item in NAV_REGISTRY]


def up(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS adm_roles (
            id         INTEGER PRIMARY KEY,
            name       TEXT NOT NULL UNIQUE,
            label      TEXT NOT NULL,
            is_system  INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS adm_role_nav (
            role_id INTEGER NOT NULL REFERENCES adm_roles(id) ON DELETE CASCADE,
            nav_key TEXT NOT NULL,
            PRIMARY KEY (role_id, nav_key)
        );
        """
    )

    # Rename users -> adm_users, guarded so re-runs are safe.
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "users" in names and "adm_users" not in names:
        conn.execute("ALTER TABLE users RENAME TO adm_users")

    conn.executemany(
        "INSERT OR IGNORE INTO adm_roles (name, label, is_system) VALUES (?,?,1)",
        [("admin", "Admin"), ("manager", "Manager"), ("viewer", "Viewer")],
    )

    keys = _nav_keys()
    for role in ("manager", "viewer"):
        rid = conn.execute("SELECT id FROM adm_roles WHERE name=?", (role,)).fetchone()[0]
        conn.executemany(
            "INSERT OR IGNORE INTO adm_role_nav (role_id, nav_key) VALUES (?,?)",
            [(rid, k) for k in keys],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_rbac_migration.py -v`
Expected: PASS (both tests). Requires `app/nav_registry.py` from Task 3 to exist.

- [ ] **Step 5: Commit**

```bash
git add migrations/0037_20260707_admin_rbac.py tests/test_admin_rbac_migration.py
git commit -m "feat(admin): migration 0037 — adm_roles/adm_role_nav + rename users->adm_users"
```

---

### Task 2: Rename `users` → `adm_users` across the code + tests

**Files:**
- Modify: `app/blueprints/auth.py` (all `users` SQL literals — 20 sites)
- Modify: `app/blueprints/stocuri_shopify.py:106` (`LEFT JOIN users u`)
- Modify: `app/blueprints/stocuri_emag.py:111` (`LEFT JOIN users u`)
- Modify: `tests/conftest.py:62` (seed INSERT), `tests/conftest.py:93` (id lookup)
- Modify: `tests/test_backup_db.py:206,215,224,232,242` (`UPDATE/SELECT users`)

**Interfaces:**
- Consumes: `adm_users` table from Task 1.
- Produces: no signature changes; only the table literal changes. `require_role`, `User` model API unchanged.

- [ ] **Step 1: Replace every `users` table reference with `adm_users`**

In `app/blueprints/auth.py`, change each SQL string that names the table. The affected fragments (search for them exactly):

```
FROM users WHERE id=?                 -> FROM adm_users WHERE id=?
FROM users WHERE username=? COLLATE   -> FROM adm_users WHERE username=? COLLATE
FROM users WHERE email=? COLLATE      -> FROM adm_users WHERE email=? COLLATE
UPDATE users SET last_login_at        -> UPDATE adm_users SET last_login_at
UPDATE users SET password_hash        -> UPDATE adm_users SET password_hash   (both occurrences)
FROM users ORDER BY id                -> FROM adm_users ORDER BY id
INSERT INTO users (username, email,   -> INSERT INTO adm_users (username, email,
FROM users WHERE id=?").fetchone()    -> FROM adm_users WHERE id=?").fetchone()   (user_edit + reset)
UPDATE users SET username=?, email=?  -> UPDATE adm_users SET username=?, email=?
SELECT username, email FROM users     -> SELECT username, email FROM adm_users
UPDATE users SET force_pw_reset=1     -> UPDATE adm_users SET force_pw_reset=1
UPDATE users SET is_active = CASE     -> UPDATE adm_users SET is_active = CASE
```

In `app/blueprints/stocuri_shopify.py` and `app/blueprints/stocuri_emag.py`:

```
LEFT JOIN users u ON u.id = s.user_id  ->  LEFT JOIN adm_users u ON u.id = s.user_id
```

In `tests/conftest.py`:

```python
# line 62
_conn.execute(
    "INSERT OR IGNORE INTO adm_users (username, email, password_hash, role) VALUES (?,?,?,?)",
    ('testadmin', 'test@test.local', generate_password_hash('testpass'), 'admin'),
)
# line 93
uid = conn.execute("SELECT id FROM adm_users WHERE username='testadmin'").fetchone()[0]
```

In `tests/test_backup_db.py`, replace all five `users` references with `adm_users` (the `UPDATE users SET email=...` and `SELECT email FROM users ...` statements).

- [ ] **Step 2: Verify no stray references remain**

Run: `grep -rniE "\b(from|into|update|join)\s+users\b" app/ tests/ migrations/0037*.py`
Expected: **no output** (historical migrations 0002/0008 still say `users` and are intentionally untouched — do not grep those).

- [ ] **Step 3: Run the full suite (validates rename + Task 1 together)**

Run: `python -m pytest -q`
Expected: PASS. `conftest.py` builds the schema via the migration runner, so `adm_users` exists and the seed + login fixtures work.

- [ ] **Step 4: Commit**

```bash
git add app/blueprints/auth.py app/blueprints/stocuri_shopify.py app/blueprints/stocuri_emag.py tests/conftest.py tests/test_backup_db.py
git commit -m "refactor(admin): rename users table -> adm_users across code + tests"
```

---

### Task 3: Nav registry — single source of truth

**Files:**
- Create: `app/nav_registry.py`
- Test: `tests/test_nav_registry.py`

**Interfaces:**
- Produces:
  - `NavItem` dataclass: `key:str, label:str, icon:str, group:str, url:str, endpoints:tuple=(), blueprint:str|None=None`
  - `NAV_REGISTRY: list[NavItem]` (ordered)
  - `GROUPS: list[str]`, `GROUP_SLUG: dict[str,str]`, `GROUP_COLLAPSIBLE: set[str]`
  - `ENDPOINT_OVERRIDES: dict[str,str]` (endpoint → nav_key, for shared-blueprint sub-routes)
  - `UNGATED_ENDPOINTS: set[str]` (business endpoints intentionally NOT gated)
- Consumed by: Task 1 (seed keys), Task 4 (authz), Task 7 (base.html render), Task 10 (matrix).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nav_registry.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "app"))
import nav_registry as nr


def test_keys_are_unique():
    keys = [i.key for i in nr.NAV_REGISTRY]
    assert len(keys) == len(set(keys))


def test_every_item_group_is_declared():
    for i in nr.NAV_REGISTRY:
        assert i.group in nr.GROUPS


def test_every_item_has_a_gate():
    # each item must declare either a blueprint or explicit endpoints
    for i in nr.NAV_REGISTRY:
        assert i.blueprint or i.endpoints, f"{i.key} has no gate"


def test_collapsible_groups_have_slugs():
    for g in nr.GROUP_COLLAPSIBLE:
        assert g in nr.GROUP_SLUG


def test_expected_keys_present():
    keys = {i.key for i in nr.NAV_REGISTRY}
    assert {"dashboard", "pnl", "preturi", "forecast", "trendyol", "ask"} <= keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_nav_registry.py -v`
Expected: FAIL — `nav_registry` not found.

- [ ] **Step 3: Write the registry**

```python
# app/nav_registry.py
"""Canonical nav-link registry — single source of truth for the sidebar,
the Admin -> Autorizari matrix, and route-level 403 enforcement.

Add a nav link HERE (never a raw <a> in base.html). Each item declares the
Flask endpoints it owns so a denied role is blocked, not just hidden.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: str                 # bootstrap-icon name, without the 'bi-' prefix
    group: str
    url: str                  # endpoint for url_for() on the link
    endpoints: tuple = ()     # endpoints this feature owns (for the 403 gate)
    blueprint: str | None = None  # shorthand: gate the whole blueprint


GROUPS = ["Analiză", "Comercial", "Operațional", "eCommerce", "Marketing", "AI"]

GROUP_SLUG = {
    "Analiză": "analiza", "Comercial": "comercial", "Operațional": "operational",
    "eCommerce": "ecommerce", "Marketing": "marketing", "AI": "ai",
}

GROUP_COLLAPSIBLE = {"Comercial", "Operațional", "eCommerce", "Marketing"}

NAV_REGISTRY = [
    NavItem("dashboard", "Dashboard", "speedometer2", "Analiză",
            "analytics.dashboard",
            endpoints=("analytics.dashboard", "reports.export_ppt_dashboard")),
    NavItem("team", "Echipă", "people-fill", "Analiză",
            "analytics.team",
            endpoints=("analytics.team", "analytics.agent_detail",
                       "reports.export_ppt_agent")),
    NavItem("clients", "Clienți", "building", "Analiză",
            "analytics.clients",
            endpoints=("analytics.clients", "analytics.client_detail",
                       "reports.export_ppt_client")),
    NavItem("products", "Produse", "box-seam-fill", "Analiză",
            "analytics.products",
            endpoints=("analytics.products", "analytics.brand_detail",
                       "reports.produs_detail")),
    NavItem("profitabilitate", "Profitabilitate", "graph-up-arrow", "Analiză",
            "reports.profitabilitate",
            endpoints=("reports.profitabilitate",
                       "reports.export_ppt_profitabilitate")),
    NavItem("pnl", "P&L", "cash-stack", "Analiză",
            "pnl.pnl", blueprint="pnl"),

    NavItem("preturi", "Prețuri", "tags-fill", "Comercial",
            "pricing.preturi",
            endpoints=("pricing.preturi", "pricing.preturi_sku")),
    NavItem("conditii", "Condiții", "file-earmark-text-fill", "Comercial",
            "pricing.conditii", endpoints=("pricing.conditii",)),
    NavItem("solduri", "Solduri", "cash-coin", "Comercial",
            "solduri.solduri", blueprint="solduri"),
    NavItem("bonus", "Bonus", "trophy-fill", "Comercial",
            "bonus.bonus", blueprint="bonus"),
    NavItem("basilur", "Basilur", "file-earmark-bar-graph-fill", "Comercial",
            "reports.raportare_basilur",
            endpoints=("reports.raportare_basilur",
                       "reports.raportare_basilur_excel",
                       "reports.raportare_basilur_ppt")),

    NavItem("forecast", "Stoc & Comenzi", "boxes", "Operațional",
            "forecast.forecast", endpoints=("forecast.forecast",)),
    NavItem("forecast_setari", "Setări Forecast", "gear-fill", "Operațional",
            "forecast.forecast_setari", endpoints=("forecast.forecast_setari",)),
    NavItem("actualizare", "Actualizare", "cloud-upload-fill", "Operațional",
            "actualizare.actualizare", blueprint="actualizare"),

    NavItem("stoc_sync", "Sincronizare Stoc", "arrow-repeat", "eCommerce",
            "stocuri_emag.stocuri_page", blueprint="stocuri_emag"),
    NavItem("trendyol", "Trendyol Pachete", "bag-fill", "eCommerce",
            "pachete.trendyol_page", endpoints=("pachete.trendyol_page",)),

    NavItem("campanii", "Campanii", "megaphone-fill", "Marketing",
            "campanii.campanii_page", blueprint="campanii"),
    NavItem("postari_ig", "Postări Instagram", "instagram", "Marketing",
            "postari.instagram", endpoints=("postari.instagram",)),
    NavItem("postari_fb", "Postări Facebook", "facebook", "Marketing",
            "postari.facebook", endpoints=("postari.facebook",)),
    NavItem("postari_auto", "Postări Auto", "robot", "Marketing",
            "postari.auto_posts_page", endpoints=("postari.auto_posts_page",)),

    NavItem("ask", "Asistent AI", "chat-dots-fill", "AI",
            "analytics.ask",
            endpoints=("analytics.ask", "analytics.api_ask")),
]

# Sub-routes of blueprints that host more than one nav item. Endpoint -> nav_key.
ENDPOINT_OVERRIDES = {
    # pricing: preturi
    "pricing.api_preturi_landing": "preturi",
    "pricing.api_preturi_vanzare": "preturi",
    "pricing.api_preturi_produs": "preturi",
    "pricing.api_preturi_curs": "preturi",
    "pricing.api_preturi_simuleaza": "preturi",
    "pricing.preturi_articol_nou": "preturi",
    "pricing.api_preturi_articol_nou": "preturi",
    "pricing.preturi_simulator": "preturi",
    "pricing.api_propunere_create": "preturi",
    "pricing.api_propunere_get": "preturi",
    "pricing.api_propunere_delete": "preturi",
    "pricing.propunere_listare_xlsx": "preturi",
    "pricing.api_client_prospect": "preturi",
    "pricing.api_produs_poza": "preturi",
    "pricing.preturi_import_oferta": "preturi",
    "pricing.api_import_oferta": "preturi",
    "pricing.propunere_oferta_xlsx": "preturi",
    "pricing.propunere_fisa_xlsx": "preturi",
    "pricing.preturi_actualizare": "preturi",
    "pricing.api_actualizare_preturi": "preturi",
    # pricing: conditii
    "pricing.api_conditii_create": "conditii",
    "pricing.api_conditii_update": "conditii",
    "pricing.api_conditii_delete": "conditii",
    "pricing.api_termene_create": "conditii",
    "pricing.api_termene_delete": "conditii",
    # forecast: working page
    "forecast.decizii": "forecast",
    "forecast.api_comenzi_drafts": "forecast",
    "forecast.api_comanda_create": "forecast",
    "forecast.api_comanda_get": "forecast",
    "forecast.api_comanda_update": "forecast",
    "forecast.api_comanda_delete": "forecast",
    "forecast.api_comanda_line_add": "forecast",
    "forecast.api_comanda_line_update": "forecast",
    "forecast.api_comanda_line_delete": "forecast",
    "forecast.api_comanda_status": "forecast",
    "forecast.api_forecast_suggest": "forecast",
    "forecast.api_forecast_sku_clients": "forecast",
    "forecast.api_forecast_chat": "forecast",
    "forecast.api_clienti_export_list": "forecast",
    "forecast.api_clienti_export_add": "forecast",
    "forecast.api_clienti_export_delete": "forecast",
    "forecast.api_clienti_search": "forecast",
    "forecast.api_termene_upsert": "forecast",
    "forecast.export_comanda": "forecast",
    "forecast.import_comanda_lines": "forecast",
    "reports.export_comanda_intern": "forecast",
    "reports.export_comanda_furnizor": "forecast",
    "reports.export_expirare_view": "forecast",
    # forecast: settings page
    "forecast.api_forecast_config_get": "forecast_setari",
    "forecast.api_forecast_config_set": "forecast_setari",
    "forecast.api_forecast_tara_save": "forecast_setari",
    "forecast.api_forecast_tara_delete": "forecast_setari",
    "forecast.api_forecast_client_save": "forecast_setari",
    "forecast.api_forecast_client_toggle": "forecast_setari",
    "forecast.api_forecast_termene_save": "forecast_setari",
    # pachete: trendyol
    "pachete.pachete_state": "trendyol",
    "pachete.pachete_products": "trendyol",
    "pachete.pachete_trendyol_preview": "trendyol",
    "pachete.pachete_trendyol_save": "trendyol",
    "pachete.pachete_trendyol_delete": "trendyol",
    "pachete.pachete_trendyol_generate_all": "trendyol",
    "pachete.pachete_trendyol_suggest": "trendyol",
    # postari: auto
    "postari.auto_posts_state": "postari_auto",
    "postari.auto_posts_upload": "postari_auto",
    "postari.auto_posts_generate": "postari_auto",
    "postari.auto_posts_regenerate": "postari_auto",
    "postari.auto_posts_approve": "postari_auto",
    "postari.auto_posts_reject": "postari_auto",
    "postari.auto_posts_settings": "postari_auto",
    "postari.auto_posts_photo": "postari_auto",
}

# Business endpoints intentionally NOT gated by the matrix (login-only).
# Doubles as the audit allowlist in Task 6.
UNGATED_ENDPOINTS = {
    "actualizare.api_actualizare_date_status",  # global import chip poll (every page)
    "reports.export_excel",                     # generic multi-feature export
    "postari.postari_ai_generate",              # shared by Instagram + Facebook pages
    # gifting is not a nav item (its sidebar link is commented out) -> login-only
    "pachete.gifting_page",
    "pachete.pachete_gifting_preview",
    "pachete.pachete_gifting_save",
    "pachete.pachete_gifting_delete",
    "pachete.pachete_gifting_suggest",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_nav_registry.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/nav_registry.py tests/test_nav_registry.py
git commit -m "feat(admin): nav_registry — canonical nav links + endpoint gate map"
```

---

### Task 4: Authorization helper

**Files:**
- Create: `app/authz.py`
- Test: `tests/test_authz.py`

**Interfaces:**
- Consumes: `nav_registry` (Task 3); `paths.DB_PATH`; `adm_roles`/`adm_role_nav` (Task 1).
- Produces:
  - `ADMIN_ROLE = "admin"`
  - `build_endpoint_map(app) -> dict[str,str]` (also stores it module-globally)
  - `endpoint_nav_key(endpoint: str) -> str | None`
  - `granted_nav_keys(role: str) -> set[str]`  (admin → all keys)
  - `can_access_nav(role: str, nav_key: str) -> bool`
  - `nav_tree(role: str) -> list[dict]` where each dict is `{"group": str, "slug": str, "collapsible": bool, "items": list[NavItem]}`
  - `all_roles() -> list[sqlite3.Row]` (id, name, label, is_system)
  - `get_matrix() -> dict[str, set[str]]` (non-admin role name → granted keys)
  - `save_matrix(grants: dict[str, list[str]]) -> None` (replaces all non-admin grants in one transaction)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_authz.py
import sqlite3
import pytest

import authz  # app/ is on sys.path via conftest
import nav_registry as nr


@pytest.fixture
def seeded(db_path):
    # conftest already ran migration 0037; ensure a custom empty role exists
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('contabil','Contabil',0)")
    c.commit(); c.close()
    yield db_path
    c = sqlite3.connect(db_path)
    c.execute("DELETE FROM adm_roles WHERE name='contabil'")
    c.execute("DELETE FROM adm_role_nav WHERE role_id NOT IN (SELECT id FROM adm_roles)")
    c.commit(); c.close()


def test_admin_sees_all_keys(seeded):
    assert authz.granted_nav_keys("admin") == {i.key for i in nr.NAV_REGISTRY}


def test_seeded_manager_sees_all(seeded):
    assert authz.granted_nav_keys("manager") == {i.key for i in nr.NAV_REGISTRY}


def test_new_role_is_deny_by_default(seeded):
    assert authz.granted_nav_keys("contabil") == set()
    assert authz.can_access_nav("contabil", "pnl") is False


def test_unknown_role_sees_nothing(seeded):
    assert authz.granted_nav_keys("does-not-exist") == set()


def test_save_and_get_matrix(seeded):
    authz.save_matrix({"contabil": ["pnl", "solduri"], "viewer": ["dashboard"]})
    m = authz.get_matrix()
    assert m["contabil"] == {"pnl", "solduri"}
    assert m["viewer"] == {"dashboard"}
    assert "admin" not in m  # admin never in the matrix


def test_nav_tree_filters_and_groups(seeded):
    authz.save_matrix({"contabil": ["pnl"]})
    tree = authz.nav_tree("contabil")
    # only the Analiză group with the pnl item survives
    assert len(tree) == 1
    assert tree[0]["group"] == "Analiză"
    assert [i.key for i in tree[0]["items"]] == ["pnl"]


def test_endpoint_map_expands_blueprint_and_overrides(flask_app):
    m = authz.build_endpoint_map(flask_app)
    assert m.get("pnl.pnl") == "pnl"           # blueprint shorthand
    assert m.get("pnl.api_upload") == "pnl"    # blueprint shorthand covers sub-routes
    assert m.get("pricing.api_conditii_create") == "conditii"  # override
    assert m.get("forecast.api_forecast_config_set") == "forecast_setari"  # override
    assert "actualizare.api_actualizare_date_status" not in m  # ungated
    assert authz.endpoint_nav_key("solduri.solduri") == "solduri"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_authz.py -v`
Expected: FAIL — `authz` not found.

- [ ] **Step 3: Write the helper**

```python
# app/authz.py
"""Role -> nav-key authorization + endpoint gate resolution.

Deny-by-default. `admin` is a superuser and bypasses every check.
"""
import sqlite3

from paths import DB_PATH
from nav_registry import (
    NAV_REGISTRY, GROUPS, GROUP_SLUG, GROUP_COLLAPSIBLE,
    ENDPOINT_OVERRIDES, UNGATED_ENDPOINTS,
)

ADMIN_ROLE = "admin"
_ALL_KEYS = {item.key for item in NAV_REGISTRY}
_endpoint_map: dict[str, str] = {}


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def build_endpoint_map(app) -> dict:
    """endpoint -> nav_key, from registry + overrides, using the app url_map.
    Call once after all blueprints are registered."""
    global _endpoint_map
    m: dict[str, str] = {}
    bp_owner = {i.blueprint: i.key for i in NAV_REGISTRY if i.blueprint}
    for rule in app.url_map.iter_rules():
        ep = rule.endpoint
        bp = ep.rsplit(".", 1)[0] if "." in ep else None
        if bp in bp_owner:
            m[ep] = bp_owner[bp]
    for item in NAV_REGISTRY:
        for ep in item.endpoints:
            m[ep] = item.key
    m.update(ENDPOINT_OVERRIDES)
    for ep in UNGATED_ENDPOINTS:
        m.pop(ep, None)
    _endpoint_map = m
    return m


def endpoint_nav_key(endpoint: str | None) -> str | None:
    if not endpoint:
        return None
    return _endpoint_map.get(endpoint)


def granted_nav_keys(role: str) -> set:
    if role == ADMIN_ROLE:
        return set(_ALL_KEYS)
    with _conn() as c:
        row = c.execute("SELECT id FROM adm_roles WHERE name=?", (role,)).fetchone()
        if not row:
            return set()
        rows = c.execute(
            "SELECT nav_key FROM adm_role_nav WHERE role_id=?", (row["id"],)
        ).fetchall()
    return {r[0] for r in rows}


def can_access_nav(role: str, nav_key: str) -> bool:
    if role == ADMIN_ROLE:
        return True
    return nav_key in granted_nav_keys(role)


def nav_tree(role: str) -> list:
    keys = granted_nav_keys(role)
    tree = []
    for g in GROUPS:
        items = [i for i in NAV_REGISTRY if i.group == g and i.key in keys]
        if items:
            tree.append({
                "group": g,
                "slug": GROUP_SLUG[g],
                "collapsible": g in GROUP_COLLAPSIBLE,
                "items": items,
            })
    return tree


def all_roles() -> list:
    with _conn() as c:
        return c.execute(
            "SELECT id, name, label, is_system FROM adm_roles "
            "ORDER BY is_system DESC, label"
        ).fetchall()


def get_matrix() -> dict:
    result = {}
    with _conn() as c:
        roles = c.execute(
            "SELECT id, name FROM adm_roles WHERE name!=?", (ADMIN_ROLE,)
        ).fetchall()
        for r in roles:
            rows = c.execute(
                "SELECT nav_key FROM adm_role_nav WHERE role_id=?", (r["id"],)
            ).fetchall()
            result[r["name"]] = {x[0] for x in rows}
    return result


def save_matrix(grants: dict) -> None:
    """Replace all non-admin grants. grants = {role_name: [nav_key, ...]}.
    Only keys in the registry and roles in the DB are persisted."""
    with _conn() as c:
        name_to_id = {
            r["name"]: r["id"]
            for r in c.execute(
                "SELECT id, name FROM adm_roles WHERE name!=?", (ADMIN_ROLE,)
            ).fetchall()
        }
        ids = list(name_to_id.values())
        if ids:
            c.execute(
                "DELETE FROM adm_role_nav WHERE role_id IN (%s)"
                % ",".join("?" * len(ids)),
                ids,
            )
        rows = []
        for role_name, keys in grants.items():
            rid = name_to_id.get(role_name)
            if rid is None:
                continue
            for k in keys:
                if k in _ALL_KEYS:
                    rows.append((rid, k))
        c.executemany(
            "INSERT OR IGNORE INTO adm_role_nav (role_id, nav_key) VALUES (?,?)",
            rows,
        )
        c.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_authz.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add app/authz.py tests/test_authz.py
git commit -m "feat(admin): authz — grants, nav_tree, endpoint gate map, matrix io"
```

---

### Task 5: Route enforcement + 403 handling

**Files:**
- Modify: `app/app.py` — call `build_endpoint_map(app)` after blueprints register; extend `before_request`; add a 403 handler; add the `nav_groups` context processor (context processor lives here too, exercised by Task 7).
- Create: `app/templates/403.html`
- Test: `tests/test_authz_enforcement.py`

**Interfaces:**
- Consumes: `authz.build_endpoint_map`, `authz.endpoint_nav_key`, `authz.can_access_nav`, `authz.nav_tree`.
- Produces: any authenticated non-admin request whose endpoint maps to a nav key they lack → 403 (JSON for `/api/`, else the 403 page).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_authz_enforcement.py
import sqlite3
import pytest
from werkzeug.security import generate_password_hash

import authz


@pytest.fixture(scope="module")
def limited_client(flask_app, db_path):
    """A user with role 'limited' granted only 'dashboard'."""
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('limited','Limited',0)")
    c.execute(
        "INSERT OR IGNORE INTO adm_users (username,email,password_hash,role) VALUES (?,?,?,?)",
        ("limited_u", "lim@test.local", generate_password_hash("limpass"), "limited"),
    )
    c.commit(); c.close()
    authz.save_matrix({"limited": ["dashboard"]})
    cl = flask_app.test_client()
    rv = cl.post("/auth/login", data={"username": "limited_u", "password": "limpass"})
    assert rv.status_code == 302
    return cl


def test_denied_page_returns_403(limited_client):
    assert limited_client.get("/pnl").status_code == 403


def test_granted_page_returns_200(limited_client):
    assert limited_client.get("/").status_code == 200  # analytics.dashboard


def test_denied_api_returns_403_json(limited_client):
    rv = limited_client.post("/pnl/api/scan")
    assert rv.status_code == 403


def test_admin_reaches_everything(client):
    # 'client' fixture is the seeded testadmin (role admin)
    assert client.get("/pnl").status_code == 200
    assert client.get("/solduri").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_authz_enforcement.py -v`
Expected: FAIL — `/pnl` returns 200 (no enforcement yet).

- [ ] **Step 3: Wire enforcement into `app.py`**

Add `abort` to the flask import at `app/app.py:10`:

```python
from flask import Flask, request, jsonify, redirect, url_for, render_template, abort
```

After the last `app.register_blueprint(pnl_bp)` (currently line 102), add:

```python
    # ── Build the endpoint -> nav_key gate map (needs all blueprints) ────────
    import authz
    authz.build_endpoint_map(app)
```

Replace the `_require_auth` body (currently `app/app.py:119-131`) so the RBAC check runs after auth:

```python
    @app.before_request
    def _require_auth():
        ep = request.endpoint or ''
        if ep in ('static', 'healthz') or ep.endswith('.static'):
            return
        if request.blueprint == 'auth':
            return
        if not current_user.is_authenticated:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized', 'code': 401}), 401
            return redirect(url_for('auth.login', next=request.full_path))
        if current_user.force_pw_reset and request.endpoint != 'auth.change_password':
            return redirect(url_for('auth.change_password'))
        # ── Nav-authorization gate (admin bypasses) ──────────────────────────
        key = authz.endpoint_nav_key(ep)
        if key and not authz.can_access_nav(current_user.role, key):
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({'error': 'Forbidden', 'code': 403}), 403
            abort(403)
```

Add a 403 handler and the nav context processor (place after the `healthz` route, near the existing template filters):

```python
    @app.errorhandler(403)
    def _forbidden(_e):
        return render_template('403.html'), 403

    @app.context_processor
    def _inject_nav():
        if current_user.is_authenticated:
            return {'nav_groups': authz.nav_tree(current_user.role)}
        return {'nav_groups': []}
```

- [ ] **Step 4: Create the 403 template**

```html
<!-- app/templates/403.html -->
{% extends 'base.html' %}
{% block title %}Acces interzis — Torb Logistic{% endblock %}
{% block content %}
<div class="text-center py-5">
  <i class="bi bi-shield-lock-fill text-danger" style="font-size:3rem"></i>
  <h4 class="mt-3">Acces interzis</h4>
  <p class="text-muted">Nu aveți permisiunea de a accesa această pagină.
     Contactați administratorul dacă aveți nevoie de acces.</p>
  <a href="{{ url_for('analytics.dashboard') }}" class="btn btn-outline-secondary btn-sm">
    <i class="bi bi-house me-1"></i> Înapoi la Dashboard
  </a>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_authz_enforcement.py -v`
Expected: PASS (4 tests). Then `python -m pytest -q` to confirm no regressions.

- [ ] **Step 6: Commit**

```bash
git add app/app.py app/templates/403.html tests/test_authz_enforcement.py
git commit -m "feat(admin): enforce nav authorization in before_request (403) + nav context"
```

---

### Task 6: Endpoint-coverage audit test

**Files:**
- Test: `tests/test_endpoint_coverage.py`

**Interfaces:**
- Consumes: `flask_app`, `authz`, `nav_registry`. No production code — this is the guardrail that makes "every feature endpoint is gated or explicitly allow-listed" enforceable, and it will fail the day someone adds an unregistered nav route (satisfies the CLAUDE.md rule from Task 11).

- [ ] **Step 1: Write the test**

```python
# tests/test_endpoint_coverage.py
import authz
import nav_registry as nr

# Blueprints whose endpoints are not business-nav pages and are governed
# elsewhere (auth) or by require_role (admin), or are framework endpoints.
_EXEMPT_BLUEPRINTS = {"auth", "admin", None}
_EXEMPT_ENDPOINTS = {"static", "healthz"}


def test_every_business_endpoint_is_gated_or_allowlisted(flask_app):
    authz.build_endpoint_map(flask_app)
    unmapped = []
    for rule in flask_app.url_map.iter_rules():
        ep = rule.endpoint
        if ep in _EXEMPT_ENDPOINTS or ep.endswith(".static"):
            continue
        bp = ep.rsplit(".", 1)[0] if "." in ep else None
        if bp in _EXEMPT_BLUEPRINTS:
            continue
        if authz.endpoint_nav_key(ep) is None and ep not in nr.UNGATED_ENDPOINTS:
            unmapped.append(ep)
    assert not unmapped, (
        "These endpoints are neither gated nor allow-listed. Assign each to a "
        "nav item (endpoints=/blueprint=/ENDPOINT_OVERRIDES) or add to "
        "UNGATED_ENDPOINTS in app/nav_registry.py:\n  " + "\n  ".join(sorted(unmapped))
    )
```

- [ ] **Step 2: Run it, resolve any gaps**

Run: `python -m pytest tests/test_endpoint_coverage.py -v`
Expected: PASS. If it FAILS, it prints each unmapped endpoint — for every one, either add it to the owning nav item / `ENDPOINT_OVERRIDES`, or add it to `UNGATED_ENDPOINTS` in `app/nav_registry.py` with a one-line reason. Re-run until green. (This step is where the registry's endpoint lists are finalized against the real url_map.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_endpoint_coverage.py app/nav_registry.py
git commit -m "test(admin): assert every business endpoint is gated or allow-listed"
```

---

### Task 7: Registry-driven sidebar

**Files:**
- Modify: `app/templates/base.html:54-172` (replace the hardcoded Analiză…AI links with a loop; keep the `Testare` block and the footer Admin block as-is)
- Test: `tests/test_nav_render.py`

**Interfaces:**
- Consumes: `nav_groups` (list of `{group,slug,collapsible,items}`) from the Task 5 context processor.
- Produces: sidebar HTML identical in structure to today for a full-access role; sections/links absent when denied.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nav_render.py
import sqlite3
import pytest
from werkzeug.security import generate_password_hash
import authz


@pytest.fixture(scope="module")
def dash_only_client(flask_app, db_path):
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('dashonly','DashOnly',0)")
    c.execute(
        "INSERT OR IGNORE INTO adm_users (username,email,password_hash,role) VALUES (?,?,?,?)",
        ("dashonly_u", "d@test.local", generate_password_hash("p"), "dashonly"),
    )
    c.commit(); c.close()
    authz.save_matrix({"dashonly": ["dashboard"]})
    cl = flask_app.test_client()
    cl.post("/auth/login", data={"username": "dashonly_u", "password": "p"})
    return cl


def test_admin_sidebar_has_pnl_link(client):
    html = client.get("/").get_data(as_text=True)
    assert "P&amp;L" in html or "P&L" in html
    assert 'data-label="Solduri"' in html


def test_limited_sidebar_hides_denied_links(dash_only_client):
    html = dash_only_client.get("/").get_data(as_text=True)
    assert 'data-label="Dashboard"' in html
    assert 'data-label="Solduri"' not in html
    assert 'data-label="P&amp;L"' not in html
    # empty groups disappear
    assert "Comercial" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_nav_render.py -v`
Expected: FAIL on `test_limited_sidebar_hides_denied_links` (links still hardcoded, always present).

- [ ] **Step 3: Replace the hardcoded nav block**

In `app/templates/base.html`, replace everything from the `<div class="sidebar-section"><span class="link-text">Analiză</span></div>` line through the AI `Asistent AI` link `</a>` (the block currently spanning lines 54–172) with this loop. Keep the `{% if show_testing %}` block above it and the footer (`sidebar-footer`) below it unchanged:

```html
    {% for grp in nav_groups %}
      {% if grp.collapsible %}
      <div class="sidebar-section sidebar-group-toggle" data-group="{{ grp.slug }}">
        <span class="link-text">{{ grp.group }}</span>
        <i class="bi bi-chevron-down sidebar-group-chevron link-text"></i>
      </div>
      <div class="sidebar-group-links" id="group-{{ grp.slug }}">
        {% for it in grp['items'] %}
        <a class="sidebar-link {% if request.endpoint == it.url %}active{% endif %}"
           href="{{ url_for(it.url) }}" data-label="{{ it.label }}">
          <i class="bi bi-{{ it.icon }}"></i><span class="link-text"> {{ it.label }}</span>
        </a>
        {% endfor %}
      </div>
      {% else %}
      <div class="sidebar-section"><span class="link-text">{{ grp.group }}</span></div>
        {% for it in grp['items'] %}
        <a class="sidebar-link {% if request.endpoint == it.url %}active{% endif %}"
           href="{{ url_for(it.url) }}" data-label="{{ it.label }}">
          <i class="bi bi-{{ it.icon }}"></i><span class="link-text"> {{ it.label }}</span>
        </a>
        {% endfor %}
      {% endif %}
    {% endfor %}
```

Notes:
- The collapsible-group JS (`data-group` / `id="group-<slug>"`) keeps working: slugs `comercial/operational/ecommerce/marketing` match the existing `localStorage` keys, so saved collapse state is preserved.
- `request.endpoint == it.url` compares the full `blueprint.endpoint` string (e.g. `analytics.dashboard`), which is what `it.url` holds — this is more correct than the previous bare-name checks.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_nav_render.py -v`
Expected: PASS (2 tests). Then `python -m pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add app/templates/base.html tests/test_nav_render.py
git commit -m "feat(admin): render sidebar from nav_registry, filtered by role grants"
```

---

### Task 8: Admin tab bar + relocate OpenClaw

**Files:**
- Create: `app/templates/admin/_tabs.html` (shared 3-tab bar)
- Modify: `app/templates/admin/users.html` (include tab bar; remove the OpenClaw card + its script; keep the users table + buttons)
- Modify: `app/templates/admin/db.html` (include tab bar; add the OpenClaw card + script here)
- Test: `tests/test_admin_tabs.py`

**Interfaces:**
- Consumes: existing `admin.users`, `admin.db_maintenance`, and the new `admin.authorizations` endpoint (Task 10 — the tab link target must exist for `url_for` to resolve; if executing strictly in order, add a stub route in Task 10 before rendering, OR implement Task 10 before Task 8's test run). Do Task 10 before running Task 8's tests.
- Produces: every admin page shows the same 3 tabs with the active one highlighted.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_tabs.py
def test_users_page_has_three_tabs(client):
    html = client.get("/admin/users").get_data(as_text=True)
    assert "Utilizatori" in html
    assert "Mentenanță DB" in html
    assert "Autorizări" in html


def test_openclaw_moved_to_db_tab(client):
    users_html = client.get("/admin/users").get_data(as_text=True)
    db_html = client.get("/admin/db").get_data(as_text=True)
    assert "OpenClaw" not in users_html
    assert "OpenClaw" in db_html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_admin_tabs.py -v`
Expected: FAIL — no tabs; OpenClaw still on users page.

- [ ] **Step 3: Create the tab bar partial**

```html
<!-- app/templates/admin/_tabs.html -->
<ul class="nav nav-tabs mb-4">
  <li class="nav-item">
    <a class="nav-link {% if active_tab == 'users' %}active{% endif %}"
       href="{{ url_for('admin.users') }}">
      <i class="bi bi-people-fill me-1"></i> Utilizatori
    </a>
  </li>
  <li class="nav-item">
    <a class="nav-link {% if active_tab == 'db' %}active{% endif %}"
       href="{{ url_for('admin.db_maintenance') }}">
      <i class="bi bi-database-fill-gear me-1"></i> Mentenanță DB
    </a>
  </li>
  <li class="nav-item">
    <a class="nav-link {% if active_tab == 'authz' %}active{% endif %}"
       href="{{ url_for('admin.authorizations') }}">
      <i class="bi bi-shield-lock-fill me-1"></i> Autorizări
    </a>
  </li>
</ul>
```

- [ ] **Step 4: Update `users.html`**

At the top of `{% block content %}` (before the existing header `div`), add:

```html
{% include 'admin/_tabs.html' with context %}
```

Set the active tab: since includes see the caller context, add a `{% set active_tab = 'users' %}` line at the very top of the `{% block content %}` (before the include). Then **delete** the OpenClaw card (the `<!-- 🦞 SECURE OPENCLAW PROXY CONTROLLER INTERFACE -->` card, currently lines 95–110) and its `<script>…</script>` block (currently lines 112–197). Keep the users table and the two header buttons.

- [ ] **Step 5: Update `db.html`**

Read `app/templates/admin/db.html` first. Add `{% set active_tab = 'db' %}` then `{% include 'admin/_tabs.html' with context %}` at the top of its content block. Append, at the end of the content block, the OpenClaw card + `<script>` moved verbatim from `users.html` (unchanged markup and JS; it uses `url_for('openclaw_ask')` and `csrf_token()` which are still valid here).

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_tabs.py -v`
Expected: PASS (2 tests). Requires Task 10's `admin.authorizations` route to exist.

- [ ] **Step 7: Commit**

```bash
git add app/templates/admin/_tabs.html app/templates/admin/users.html app/templates/admin/db.html tests/test_admin_tabs.py
git commit -m "feat(admin): 3-tab admin shell; move OpenClaw console to Mentenanță DB"
```

---

### Task 9: Roles CRUD (Utilizatori tab)

**Files:**
- Create: `app/blueprints/admin_roles.py` (routes on the existing `admin_bp`)
- Create: `app/templates/admin/role_form.html`
- Modify: `app/app.py:24` area — import `admin_roles` for side effects (like `admin_db`)
- Modify: `app/blueprints/auth.py` — make `UserForm.role` choices dynamic (from `adm_roles`); render a role badge generically in `users.html`
- Modify: `app/templates/admin/users.html` — add the roles panel + "Rol nou" button; generic role badge
- Test: `tests/test_admin_roles.py`

**Interfaces:**
- Consumes: `authz.all_roles`, `adm_roles`, `adm_users`.
- Produces: routes `admin.roles` list is folded into `admin.users`; `admin.role_new` (GET/POST), `admin.role_edit` (GET/POST), `admin.role_delete` (POST). A `RoleForm` (WTForms) with `name` (slug) + `label`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_roles.py
import sqlite3


def test_create_role(client, db_path):
    rv = client.post("/admin/roles/new",
                     data={"name": "contabil", "label": "Contabil"},
                     follow_redirects=True)
    assert rv.status_code == 200
    c = sqlite3.connect(db_path)
    row = c.execute("SELECT label, is_system FROM adm_roles WHERE name='contabil'").fetchone()
    c.close()
    assert row == ("Contabil", 0)


def test_cannot_delete_system_role(client, db_path):
    c = sqlite3.connect(db_path)
    aid = c.execute("SELECT id FROM adm_roles WHERE name='admin'").fetchone()[0]
    c.close()
    client.post(f"/admin/roles/{aid}/delete", follow_redirects=True)
    c = sqlite3.connect(db_path)
    still = c.execute("SELECT COUNT(*) FROM adm_roles WHERE name='admin'").fetchone()[0]
    c.close()
    assert still == 1


def test_cannot_delete_role_in_use(client, db_path):
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('inuse','InUse',0)")
    rid = c.execute("SELECT id FROM adm_roles WHERE name='inuse'").fetchone()[0]
    c.execute("INSERT OR IGNORE INTO adm_users (username,email,password_hash,role) VALUES ('u_inuse','x@x.l','h','inuse')")
    c.commit(); c.close()
    client.post(f"/admin/roles/{rid}/delete", follow_redirects=True)
    c = sqlite3.connect(db_path)
    still = c.execute("SELECT COUNT(*) FROM adm_roles WHERE name='inuse'").fetchone()[0]
    c.close()
    assert still == 1


def test_delete_unused_custom_role(client, db_path):
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('temp','Temp',0)")
    rid = c.execute("SELECT id FROM adm_roles WHERE name='temp'").fetchone()[0]
    c.commit(); c.close()
    client.post(f"/admin/roles/{rid}/delete", follow_redirects=True)
    c = sqlite3.connect(db_path)
    gone = c.execute("SELECT COUNT(*) FROM adm_roles WHERE name='temp'").fetchone()[0]
    c.close()
    assert gone == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_admin_roles.py -v`
Expected: FAIL — routes don't exist (404).

- [ ] **Step 3: Add a dynamic `RoleForm` and make `UserForm.role` dynamic**

In `app/blueprints/auth.py`, after the `EditUserForm` class, add:

```python
import re


class RoleForm(FlaskForm):
    name = StringField("Nume (slug)", validators=[DataRequired(), Length(min=2, max=32)])
    label = StringField("Etichetă", validators=[DataRequired(), Length(min=2, max=48)])


def role_choices():
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT name, label FROM adm_roles ORDER BY label").fetchall()
    return [(r["name"], r["label"]) for r in rows]


SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")
```

Change `UserForm` so its `role` choices are populated at instantiation (replace the static `SelectField(... choices=[...])`):

```python
class UserForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=32)])
    email = StringField("Email", validators=[DataRequired()])
    role = SelectField("Rol")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.role.choices = role_choices()
```

`EditUserForm(UserForm)` keeps inheriting the dynamic choices.

- [ ] **Step 4: Write the roles blueprint**

```python
# app/blueprints/admin_roles.py
"""Role management routes (create/edit-label/delete) on admin_bp.

Imported for side effects in app.py before admin_bp is registered.
"""
import sqlite3

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from paths import DB_PATH
from blueprints.auth import RoleForm, SLUG_RE, _log, admin_bp, require_role


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


@admin_bp.route("/roles/new", methods=["GET", "POST"])
@require_role("admin")
def role_new():
    form = RoleForm()
    if form.validate_on_submit():
        name = form.name.data.strip().lower()
        if not SLUG_RE.match(name):
            form.name.errors.append("Slug invalid: doar litere mici, cifre, underscore.")
        else:
            try:
                with _conn() as c:
                    c.execute(
                        "INSERT INTO adm_roles (name, label, is_system) VALUES (?,?,0)",
                        (name, form.label.data.strip()),
                    )
                _log(current_user.id, "role_created", request.remote_addr or "0.0.0.0", name)
                flash("Rol creat.", "success")
                return redirect(url_for("admin.users"))
            except sqlite3.IntegrityError:
                form.name.errors.append("Nume de rol deja existent.")
    return render_template("admin/role_form.html", form=form, title="Rol nou",
                           action=url_for("admin.role_new"))


@admin_bp.route("/roles/<int:rid>/edit", methods=["GET", "POST"])
@require_role("admin")
def role_edit(rid):
    with _conn() as c:
        row = c.execute("SELECT * FROM adm_roles WHERE id=?", (rid,)).fetchone()
    if not row:
        flash("Rol inexistent.", "warning")
        return redirect(url_for("admin.users"))
    form = RoleForm()
    if request.method == "GET":
        form.name.data = row["name"]
        form.label.data = row["label"]
    if form.validate_on_submit():
        # name (slug) is immutable after creation — only label changes
        with _conn() as c:
            c.execute("UPDATE adm_roles SET label=? WHERE id=?",
                      (form.label.data.strip(), rid))
        _log(current_user.id, "role_edited", request.remote_addr or "0.0.0.0", row["name"])
        flash("Rol actualizat.", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/role_form.html", form=form,
                           title="Editare rol", action=url_for("admin.role_edit", rid=rid),
                           name_locked=True)


@admin_bp.route("/roles/<int:rid>/delete", methods=["POST"])
@require_role("admin")
def role_delete(rid):
    from flask_wtf.csrf import validate_csrf
    try:
        validate_csrf(request.form.get("csrf_token"))
    except Exception:
        from flask import abort
        abort(403)
    with _conn() as c:
        row = c.execute("SELECT name, is_system FROM adm_roles WHERE id=?", (rid,)).fetchone()
        if not row:
            flash("Rol inexistent.", "warning")
            return redirect(url_for("admin.users"))
        if row["is_system"]:
            flash("Rolurile de sistem nu pot fi șterse.", "warning")
            return redirect(url_for("admin.users"))
        in_use = c.execute("SELECT COUNT(*) FROM adm_users WHERE role=?", (row["name"],)).fetchone()[0]
        if in_use:
            flash(f"Rolul este atribuit la {in_use} utilizator(i). Reatribuiți-i întâi.", "warning")
            return redirect(url_for("admin.users"))
        c.execute("DELETE FROM adm_roles WHERE id=?", (rid,))  # cascade clears adm_role_nav
    _log(current_user.id, "role_deleted", request.remote_addr or "0.0.0.0", row["name"])
    flash("Rol șters.", "success")
    return redirect(url_for("admin.users"))
```

- [ ] **Step 5: Register the blueprint module for side effects**

In `app/app.py`, next to `from blueprints import admin_db  # noqa: F401 ...` (line 24), add:

```python
    from blueprints import admin_roles  # noqa: F401 — attaches /admin/roles routes to admin_bp
```

- [ ] **Step 6: Create `role_form.html`**

```html
<!-- app/templates/admin/role_form.html -->
{% extends 'base.html' %}
{% block title %}{{ title }} — Torb Logistic{% endblock %}
{% block content %}
<div class="row justify-content-center">
  <div class="col-md-6 col-lg-5">
    <div class="d-flex align-items-center mb-3 gap-2">
      <a href="{{ url_for('admin.users') }}" class="btn btn-sm btn-outline-secondary">
        <i class="bi bi-arrow-left"></i></a>
      <h5 class="mb-0">{{ title }}</h5>
    </div>
    <div class="card shadow-sm"><div class="card-body p-4">
      <form method="POST" action="{{ action }}" novalidate>
        {{ form.hidden_tag() }}
        <div class="mb-3">
          {{ form.name.label(class="form-label small fw-semibold") }}
          {{ form.name(class="form-control" + (' is-invalid' if form.name.errors else ''),
                       readonly=name_locked|default(false)) }}
          {% for err in form.name.errors %}<div class="invalid-feedback">{{ err }}</div>{% endfor %}
          <div class="form-text">Slug: litere mici, cifre, underscore. Fix după creare.</div>
        </div>
        <div class="mb-4">
          {{ form.label.label(class="form-label small fw-semibold") }}
          {{ form.label(class="form-control" + (' is-invalid' if form.label.errors else '')) }}
          {% for err in form.label.errors %}<div class="invalid-feedback">{{ err }}</div>{% endfor %}
        </div>
        <button type="submit" class="btn btn-success w-100">
          <i class="bi bi-check-circle me-1"></i> Salvează</button>
      </form>
    </div></div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 7: Add the roles panel to `users.html` + generic badge**

Change the users-table role cell (currently the `{% if u.role == 'admin' %}…{% endif %}` badge block) to a generic badge:

```html
<td><span class="badge bg-secondary">{{ u.role }}</span></td>
```

After the users `card` (before the OpenClaw removal from Task 8, i.e. where OpenClaw used to be), add a roles panel. The `admin.users` route must pass `roles=authz.all_roles()` — update it in `app/blueprints/auth.py`:

```python
@admin_bp.route("/users")
@require_role("admin")
def users():
    import authz
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT id, username, email, role, is_active, last_login_at, created_at"
            " FROM adm_users ORDER BY id"
        ).fetchall()
    return render_template("admin/users.html", users=rows, roles=authz.all_roles())
```

Roles panel markup (uses `roles`):

```html
<div class="d-flex justify-content-between align-items-center mb-3 mt-4">
  <h6 class="mb-0"><i class="bi bi-shield-lock-fill me-2 text-primary"></i>Roluri</h6>
  <a href="{{ url_for('admin.role_new') }}" class="btn btn-success btn-sm">
    <i class="bi bi-plus-circle me-1"></i> Rol nou</a>
</div>
<div class="card shadow-sm mb-4"><div class="table-responsive">
  <table class="table table-hover align-middle mb-0">
    <thead class="table-dark"><tr>
      <th>Etichetă</th><th>Slug</th><th>Tip</th><th class="text-end">Acțiuni</th>
    </tr></thead>
    <tbody>
      {% for r in roles %}
      <tr>
        <td class="fw-semibold">{{ r.label }}</td>
        <td class="small text-muted">{{ r.name }}</td>
        <td>{% if r.is_system %}<span class="badge bg-dark">Sistem</span>
            {% else %}<span class="badge bg-secondary">Personalizat</span>{% endif %}</td>
        <td class="text-end">
          <a href="{{ url_for('admin.role_edit', rid=r.id) }}"
             class="btn btn-sm btn-outline-secondary me-1" title="Editare">
            <i class="bi bi-pencil"></i></a>
          {% if not r.is_system %}
          <form method="POST" action="{{ url_for('admin.role_delete', rid=r.id) }}"
                class="d-inline" onsubmit="return confirm('Ștergeți rolul {{ r.label }}?')">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button class="btn btn-sm btn-outline-danger" title="Ștergere">
              <i class="bi bi-trash"></i></button>
          </form>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div></div>
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_roles.py -v`
Expected: PASS (4 tests). Then `python -m pytest -q`.

- [ ] **Step 9: Commit**

```bash
git add app/blueprints/admin_roles.py app/templates/admin/role_form.html app/app.py app/blueprints/auth.py app/templates/admin/users.html tests/test_admin_roles.py
git commit -m "feat(admin): role CRUD + dynamic role choices + roles panel"
```

---

### Task 10: Autorizări matrix page

**Files:**
- Create: `app/blueprints/admin_authz.py` (routes on `admin_bp`)
- Create: `app/templates/admin/authorizations.html`
- Modify: `app/app.py:24` area — import `admin_authz` for side effects
- Test: `tests/test_admin_authz_page.py`

**Interfaces:**
- Consumes: `authz.all_roles`, `authz.get_matrix`, `authz.save_matrix`, `nav_registry.NAV_REGISTRY`, `GROUPS`.
- Produces: `admin.authorizations` (GET renders matrix, POST saves). This endpoint is the tab target referenced in Task 8 — implement this task before running Task 8's tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_authz_page.py
import sqlite3
import authz


def test_matrix_page_renders(client, db_path):
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('mkt','Marketing',0)")
    c.commit(); c.close()
    html = client.get("/admin/authorizations").get_data(as_text=True)
    assert "Autorizări" in html
    assert "Marketing" in html   # role column header (label)
    assert "P&amp;L" in html or "P&L" in html  # a nav-item row


def test_matrix_post_saves_grants(client, db_path):
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('acc','Contabil',0)")
    c.commit(); c.close()
    # grant acc -> pnl + solduri via checkbox fields "grant:<role>:<navkey>"
    client.post("/admin/authorizations", data={
        "grant:acc:pnl": "on",
        "grant:acc:solduri": "on",
    }, follow_redirects=True)
    assert authz.get_matrix()["acc"] == {"pnl", "solduri"}


def test_admin_role_not_a_column(client):
    html = client.get("/admin/authorizations").get_data(as_text=True)
    # admin must not be an editable column
    assert "grant:admin:" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_admin_authz_page.py -v`
Expected: FAIL — route missing (404).

- [ ] **Step 3: Write the matrix blueprint**

```python
# app/blueprints/admin_authz.py
"""Autorizări (role -> nav) matrix page on admin_bp.

Imported for side effects in app.py before admin_bp is registered.
"""
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

import authz
from nav_registry import NAV_REGISTRY, GROUPS
from blueprints.auth import _log, admin_bp, require_role


@admin_bp.route("/authorizations", methods=["GET", "POST"])
@require_role("admin")
def authorizations():
    roles = [r for r in authz.all_roles() if r["name"] != authz.ADMIN_ROLE]

    if request.method == "POST":
        grants = {r["name"]: [] for r in roles}
        for field in request.form:
            # fields look like "grant:<role>:<navkey>"
            if not field.startswith("grant:"):
                continue
            _, role_name, nav_key = field.split(":", 2)
            if role_name in grants:
                grants[role_name].append(nav_key)
        authz.save_matrix(grants)
        _log(current_user.id, "authz_saved", request.remote_addr or "0.0.0.0")
        flash("Autorizări salvate.", "success")
        return redirect(url_for("admin.authorizations"))

    matrix = authz.get_matrix()  # {role_name: set(nav_key)}
    groups = []
    for g in GROUPS:
        items = [i for i in NAV_REGISTRY if i.group == g]
        if items:
            groups.append({"group": g, "items": items})
    return render_template(
        "admin/authorizations.html", roles=roles, groups=groups, matrix=matrix,
    )
```

- [ ] **Step 4: Register the module for side effects**

In `app/app.py`, near the other admin imports (line 24 area):

```python
    from blueprints import admin_authz  # noqa: F401 — attaches /admin/authorizations
```

- [ ] **Step 5: Create the matrix template**

```html
<!-- app/templates/admin/authorizations.html -->
{% extends 'base.html' %}
{% block title %}Autorizări — Torb Logistic{% endblock %}
{% block content %}
{% set active_tab = 'authz' %}
{% include 'admin/_tabs.html' with context %}

<div class="d-flex justify-content-between align-items-center mb-3">
  <h5 class="mb-0"><i class="bi bi-shield-lock-fill me-2 text-primary"></i>Autorizări meniu</h5>
</div>

{% with messages = get_flashed_messages(with_categories=true) %}
  {% for cat, msg in messages %}<div class="alert alert-{{ cat }} py-2">{{ msg }}</div>{% endfor %}
{% endwith %}

{% if not roles %}
<div class="alert alert-info">Niciun rol personalizabil. Adăugați roluri în tab-ul Utilizatori.
  (Rolul <strong>admin</strong> are acces complet și nu apare aici.)</div>
{% else %}
<form method="POST" action="{{ url_for('admin.authorizations') }}">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <div class="card shadow-sm"><div class="table-responsive">
    <table class="table table-hover align-middle mb-0">
      <thead class="table-dark"><tr>
        <th>Element meniu</th>
        {% for r in roles %}<th class="text-center">{{ r.label }}</th>{% endfor %}
      </tr></thead>
      <tbody>
        {% for grp in groups %}
        <tr class="table-secondary"><td colspan="{{ roles|length + 1 }}"
            class="fw-semibold small text-uppercase">{{ grp.group }}</td></tr>
        {% for it in grp['items'] %}
        <tr>
          <td><i class="bi bi-{{ it.icon }} me-2 text-muted"></i>{{ it.label }}</td>
          {% for r in roles %}
          <td class="text-center">
            <input type="checkbox" class="form-check-input"
                   name="grant:{{ r.name }}:{{ it.key }}"
                   {% if it.key in matrix.get(r.name, []) %}checked{% endif %}>
          </td>
          {% endfor %}
        </tr>
        {% endfor %}
        {% endfor %}
      </tbody>
    </table>
  </div></div>
  <button type="submit" class="btn btn-success mt-3">
    <i class="bi bi-check-circle me-1"></i> Salvează autorizările</button>
</form>
{% endif %}
{% endblock %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_authz_page.py -v`
Expected: PASS (3 tests). Then run Task 8's `tests/test_admin_tabs.py` (now that `admin.authorizations` exists) and the full suite `python -m pytest -q`.

- [ ] **Step 7: Commit**

```bash
git add app/blueprints/admin_authz.py app/templates/admin/authorizations.html app/app.py tests/test_admin_authz_page.py
git commit -m "feat(admin): Autorizări matrix — edit role→nav grants"
```

---

### Task 11: Docs + CLAUDE.md rule

**Files:**
- Modify: `CLAUDE.md` (add the nav-registry rule)
- Modify: `CHANGELOG.md` (`[Unreleased]` entry)
- Modify: `context/STATUS.md` (state change)

**Interfaces:** none (documentation).

- [ ] **Step 1: Add the rule to `CLAUDE.md`**

Under "### Rules when creating new files", add a bullet:

```markdown
- **Adding a nav menu link** → register it in `app/nav_registry.py` (`NAV_REGISTRY`) with its `endpoints`/`blueprint`; never add a raw `<a>` nav link to `base.html`. Registration auto-lists it in **Admin → Autorizări** and turns on its `403` route enforcement. New links are deny-by-default until granted in the matrix. `tests/test_endpoint_coverage.py` fails if a new business endpoint is left un-gated and un-allowlisted.
```

- [ ] **Step 2: Add a `CHANGELOG.md` `[Unreleased]` entry**

```markdown
### Added
- Admin RBAC: dynamic roles (`adm_roles`) + role→nav authorization matrix
  (Admin → Autorizări). Sidebar links and their routes are now gated per role
  (deny-by-default; `admin` is a superuser). Admin module reorganized into three
  tabs (Utilizatori, Mentenanță DB, Autorizări).

### Changed
- Renamed `users` table to `adm_users`; new admin tables use the `adm_` prefix.
- Sidebar is now rendered from a canonical `app/nav_registry.py` (single source
  of truth for links, the matrix, and 403 enforcement).
```

- [ ] **Step 3: Update `context/STATUS.md`**

Replace the "Next immediate step" / in-progress section with a note that the Admin RBAC module shipped (dynamic roles + nav authorization matrix + `adm_` rename), and record any follow-ups (e.g. reassign-users-before-delete UX, optional gating of `postari_ai_generate`).

- [ ] **Step 4: Run the full suite one last time**

Run: `python -m pytest -q`
Expected: PASS (all tests, including migration/authz/enforcement/coverage/tabs/roles/matrix).

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md CHANGELOG.md context/STATUS.md
git commit -m "docs(admin): nav-registry rule + RBAC changelog/status"
```

---

## Self-Review

**Spec coverage:**
- 3 tabs → Tasks 8 (shell), 9 (Utilizatori/roles), 10 (Autorizări); Mentenanță DB retained + OpenClaw moved (Task 8). ✓
- Dynamic roles (D1) → Tasks 1, 9. ✓
- Hide + block/403 (D2) → Tasks 5, 6, 7. ✓
- Admin superuser (D3) → `authz` (Task 4), enforcement bypass (Task 5), excluded matrix column (Task 10). ✓
- Per-link matrix + deny-by-default + seed (D4/D5/D6) → Tasks 1 (seed), 4 (deny-by-default), 10 (editor). ✓
- Registry-driven sync (D7) → Tasks 3, 7; coverage guard (Task 6). ✓
- `adm_` naming + `users` rename (D8) → Tasks 1, 2. ✓
- CLAUDE.md rule → Task 11. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; every test step shows assertions. ✓

**Type/name consistency:** `nav_tree` dict keys (`group/slug/collapsible/items`) consistent between Task 4 (producer) and Task 7 (consumer). `save_matrix(grants: dict[str,list])` / `get_matrix()->dict[str,set]` consistent between Tasks 4 and 10. Checkbox field format `grant:<role>:<navkey>` consistent between Task 10 template and route. `endpoint_nav_key`/`can_access_nav`/`build_endpoint_map` names consistent across Tasks 4, 5, 6. ✓

**Ordering caveat (flagged in-task):** Task 1's seed and Task 8's tab link depend on Tasks 3 and 10 respectively. Notes in those tasks tell the implementer to author `nav_registry.py` (Task 3) before Task 1's test run, and `admin.authorizations` (Task 10) before Task 8's test run. If executing purely sequentially 1→11, do Task 3 before Task 1's Step 4, and Task 10 before Task 8's Step 6.
