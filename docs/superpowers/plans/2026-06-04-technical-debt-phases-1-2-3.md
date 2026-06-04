# Technical Debt — Phases 1, 2, 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up dead code, harden CI/CD migrations, fix the AI model default, wire tests to the real schema, and split `app/queries.py` (3,236 lines) into focused domain modules — all without breaking existing behaviour.

**Architecture:** Phase 1 is pure deletion/one-liners. Phase 2 replaces the hand-maintained test schema with the migration runner. Phase 3 converts `app/queries.py` into a `app/queries/` package whose `__init__.py` re-exports every function — so all `import queries` callsites are untouched.

**Tech Stack:** Python 3.11, Flask, SQLite, pytest, ruff, GitHub Actions

---

## Domain map for Phase 3 (queries package)

| Module | Functions |
|---|---|
| `_shared.py` | `current_year`, `prior_year`, `display_years`, `_years_params`, `max_luna_for_year`, `get_sku_cod_mare_map`, `rebuild_cond_resolved`, `ensure_cond_resolved`, `furnizori_list`, `agents_list`, `brands_list`, `_agents_list_cached`, `_brands_list_cached`, `_COND_RESOLVED_DDL`, `_COND_RESOLVED_REBUILD` |
| `analytics.py` | `kpi_cards`, `kpi_luna_curenta`, `monthly_trend`, `brand_mix`, `channel_mix`, `risk_kaufland`, `risk_agent`, `churn_clients`, `top_clients`, `team_table`, `agent_kpi`, `agent_monthly_trend`, `agent_clients`, `agent_top_skus`, `agent_clients_full`, `agent_brands_full`, `agent_skus_full`, `agent_brand_sku_monthly`, `agent_monthly_full`, `agent_monthly_base`, `agent_monthly_all_years`, `agent_brand_monthly`, `profitabilitate_agenti`, `profitabilitate_clienti`, `profitabilitate_produse`, `profitabilitate_matrice` |
| `clients.py` | `clients_list`, `client_info`, `client_orders`, `client_brand_mix`, `client_yearly`, `client_products_full`, `client_yearly_full`, `client_monthly_full` |
| `products.py` | `products_brands`, `products_top_skus`, `brand_monthly_full`, `brand_kpi`, `brand_clients`, `product_kpi`, `product_clients`, `product_monthly`, `product_yearly`, `sku_clients_monthly` |
| `pricing.py` | `preturi_catalog`, `preturi_sku`, `preturi_client_sku`, `preturi_update_landing`, `preturi_update_vanzare`, `preturi_update_produs`, `rate_schimb_list`, `rate_schimb_update`, `conditii_list`, `conditii_get`, `conditii_create`, `conditii_update`, `conditii_delete`, `termene_list`, `termene_create`, `termene_delete`, `marja_ajustata` |
| `orders.py` | `termene_aprovizionare_list`, `termene_partial_update`, `termene_aprovizionare_upsert`, `comenzi_list`, `comanda_get`, `comanda_create`, `comanda_update`, `comanda_delete`, `comanda_line_upsert`, `comanda_line_update`, `comanda_line_delete` |
| `forecast.py` | `forecast_stoc`, `forecast_summary`, `forecast_gama_list`, `forecast_stoc_brand`, `forecast_stoc_extended`, `forecast_brands_list`, `basilur_monthly_per_brand`, `basilur_kpi_per_brand`, `basilur_kpi_total`, `basilur_stoc_per_brand`, `basilur_stoc_total`, `basilur_stoc_detail`, `basilur_monthly_trend` |
| `bonus.py` | `bonus_team` |
| `export.py` | `get_export_hu_codes`, `monthly_sales_ro_hu`, `stoc_ro_hu`, `in_transit_ro_hu`, `expirare_list`, `tari_export_list`, `tari_export_upsert`, `tari_export_delete`, `clienti_export_list`, `clienti_export_upsert`, `clienti_export_toggle` |

---

## Task 1: Delete dead code + fix AI model

**Files:**
- Delete: `etl/init_forecast_tables.py`
- Modify: `app/config.py`

- [ ] **Step 1: Verify nothing imports init_forecast_tables**

```bash
grep -r "init_forecast_tables" . --include="*.py" --exclude-dir=.venv
```
Expected output: no matches (the file is a standalone script, nothing imports it).

- [ ] **Step 2: Delete the dead script**

```powershell
Remove-Item etl\init_forecast_tables.py
```

- [ ] **Step 3: Update AI model default in `app/config.py`**

In `app/config.py`, change line:
```python
    ai_model: str = "claude-opus-4-7"
```
to:
```python
    ai_model: str = "claude-sonnet-4-6"
```

- [ ] **Step 4: Run tests to confirm nothing broke**

```bash
pytest tests/ -q
```
Expected: `66 passed`

- [ ] **Step 5: Lint**

```bash
ruff check .
```
Expected: no output (zero violations).

- [ ] **Step 6: Commit**

```
git add app/config.py
git rm etl/init_forecast_tables.py
git commit -m "chore: delete dead init_forecast_tables script, update default AI model to claude-sonnet-4-6"
```

---

## Task 2: Harden CI/CD — explicit migration step before restart

**Files:**
- Modify: `.github/workflows/deploy_VPS.yml` (the `deploy` job `script:` block)

**Context:** Currently `systemctl restart torb-py` restarts the app and migrations run inside Flask startup. If a migration raises an exception, Flask crashes in production rather than the deploy aborting. Adding an explicit `python migrations/runner.py data/torb.db` before the restart — under `set -e` — means a failed migration aborts the SSH session with a non-zero exit, which fails the GitHub Actions step, which blocks the deploy and leaves the current service running.

- [ ] **Step 1: Add explicit migration run to deploy script**

In `.github/workflows/deploy_VPS.yml`, find the `script:` block inside the `deploy` job. It currently ends with:

```yaml
            # Restart app (migrations run automatically on startup)
            sudo systemctl restart torb-py
```

Replace those two lines with:

```yaml
            # Run migrations explicitly — a failure here aborts deploy and leaves service running
            python migrations/runner.py data/torb.db

            # Restart app
            sudo systemctl restart torb-py
```

- [ ] **Step 2: Verify the YAML is valid**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy_VPS.yml'))" && echo "YAML OK"
```
Expected: `YAML OK`

- [ ] **Step 3: Commit**

```
git add .github/workflows/deploy_VPS.yml
git commit -m "ci: run migrations explicitly before service restart to abort deploy on migration failure"
```

---

## Task 3: Wire conftest.py to the migration runner

**Files:**
- Modify: `tests/conftest.py`

**Context:** `tests/conftest.py` has a 289-line hand-maintained `_SCHEMA` string that duplicates the migration SQL. It has already drifted: it uses the old `v_clienti` definition from migration 0001 (not 0003's fixed version), and it is missing migration 0004's 6 forecast tables. Every time a migration is added, the test schema must be manually kept in sync — and this sync is currently broken. Replacing it with `run_all()` from the migration runner ensures tests always exercise the real schema automatically.

The `conftest.py` currently:
1. Creates a temp SQLite file
2. Patches `DB_PATH` on `paths`, `db` modules
3. Runs `_conn.executescript(_SCHEMA)` — the big hand-written block
4. Seeds reference data and test transactions

After this change:
- Steps 1 and 2 stay the same
- Step 3 becomes `run_all(_TEST_DB)` (one line)
- Step 4 seeds stay the same (they live outside the schema block)

- [ ] **Step 1: Run tests first to record the baseline**

```bash
pytest tests/ -v 2>&1 | tail -5
```
Expected: `66 passed`

- [ ] **Step 2: Replace the schema block in `tests/conftest.py`**

Find and remove the entire `_SCHEMA = """..."""` constant (lines 34–289) and the two lines that use it:
```python
_conn = sqlite3.connect(_TEST_DB)
_conn.executescript(_SCHEMA)
```

Replace with:
```python
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.join(ROOT, 'migrations'))
from runner import run_all as _run_all  # noqa: E402
_run_all(_TEST_DB)
_conn = sqlite3.connect(_TEST_DB)
```

The seed block that follows (`_conn.execute("INSERT OR IGNORE INTO tari_export ...")`, transactions seed, user seed, `_conn.commit()`, `_conn.close()`) remains unchanged.

The full replacement section (replacing `_SCHEMA = """` through `_conn.close()` before the fixtures) should look like:

```python
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.join(ROOT, 'migrations'))
from runner import run_all as _run_all  # noqa: E402
_run_all(_TEST_DB)

_conn = sqlite3.connect(_TEST_DB)

# Seed tari_export (required by clienti_export FK)
_conn.execute("INSERT OR IGNORE INTO tari_export (tara, piata) VALUES ('Ungaria','HU')")

# Seed minimal transactions so dashboard KPI queries return numbers, not None
_SEED_TX = [
    (1, 2026, '2026-01-15', 'DL001', 'F001', 'P001', 'SKU001', 'Basilur',
     10, 50.0, 0.09, 30.0, 545.0, 500.0, 300.0, 200.0, 0.0,
     'Client Test', 'C001', 'Agent Test'),
    (1, 2026, '2026-01-20', 'DL002', 'F002', 'P002', 'SKU002', 'Toras',
     5, 80.0, 0.09, 50.0, 436.0, 400.0, 250.0, 150.0, 0.0,
     'KAUFLAND ROMANIA', 'KAUFLAND', 'Agent Test'),
]
for tx in _SEED_TX:
    _conn.execute("""
        INSERT OR IGNORE INTO tranzactii
        (luna, an, data_dl, nr_dl, nr_factura, cod_produs, sku, furnizor,
         cantitate, pret_vanzare, tva_pct, pret_cumparare,
         val_bruta, val_neta, val_achizitie, marja_bruta, discount_pct,
         client, cod_client, agent)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, tx)

from werkzeug.security import generate_password_hash  # noqa: E402

_conn.execute(
    "INSERT OR IGNORE INTO users (username, email, password_hash, role) VALUES (?,?,?,?)",
    ('testadmin', 'test@test.local', generate_password_hash('testpass'), 'admin'),
)
_conn.commit()
_conn.close()
```

- [ ] **Step 3: Run tests — must still pass**

```bash
pytest tests/ -v 2>&1 | tail -10
```
Expected: `66 passed`. If any test fails, the migration runner produced a different schema than the old hand-written one — investigate the diff before proceeding.

- [ ] **Step 4: Lint**

```bash
ruff check .
```
Expected: no output.

- [ ] **Step 5: Commit**

```
git add tests/conftest.py
git commit -m "test: replace hand-maintained conftest schema with migration runner — always in sync"
```

---

## Task 4: Split queries.py into domain package

**Files:**
- Create: `app/queries/__init__.py`
- Create: `app/queries/_shared.py`
- Create: `app/queries/analytics.py`
- Create: `app/queries/clients.py`
- Create: `app/queries/products.py`
- Create: `app/queries/pricing.py`
- Create: `app/queries/orders.py`
- Create: `app/queries/forecast.py`
- Create: `app/queries/bonus.py`
- Create: `app/queries/export.py`
- Delete: `app/queries.py`

**Key constraint:** All blueprints do `import queries` and then call `queries.some_function()`. The new `app/queries/__init__.py` must export every public function so callsites are untouched. Since `app/` is on `sys.path` (set in `app.py`), `import queries` will find `app/queries/__init__.py` automatically once `app/queries.py` is removed.

### Step sequence

- [ ] **Step 4.0: Record test baseline**

```bash
pytest tests/ -q 2>&1 | tail -3
```
Expected: `66 passed`

- [ ] **Step 4.1: Create the `app/queries/` directory**

```powershell
New-Item -ItemType Directory -Path app\queries
```

- [ ] **Step 4.2: Create `app/queries/_shared.py`**

This module contains date helpers, the materialized condition table logic, and cached lookup lists. Copy lines 1–117 from `app/queries.py` (everything up to and including `ensure_cond_resolved`) plus `furnizori_list` (L1043–1048), `_agents_list_cached`/`agents_list` (L516–527), `_brands_list_cached`/`brands_list` (L529–537), and `max_luna_for_year` (L281–284).

```python
# app/queries/_shared.py
import datetime
from functools import lru_cache
from db import query, query_one, get_db


def current_year():
    return datetime.date.today().year


def prior_year():
    return datetime.date.today().year - 1


def display_years():
    y = datetime.date.today().year
    return (y - 2, y - 1, y)


def _years_params(years=None):
    yrs = years or display_years()
    return {f'y{i}': v for i, v in enumerate(yrs)}


def max_luna_for_year(an):
    # [exact body from app/queries.py L281-284]
    ...


def get_sku_cod_mare_map() -> dict:
    # [exact body from app/queries.py L26-41]
    ...


_COND_RESOLVED_DDL = """..."""  # exact from queries.py L60-69
_COND_RESOLVED_REBUILD = """..."""  # exact from queries.py L71-87


def rebuild_cond_resolved(conn=None):
    # [exact body from app/queries.py L90-104]
    ...


def ensure_cond_resolved():
    # [exact body from app/queries.py L106-117]
    ...


def furnizori_list():
    # [exact body from app/queries.py L1043-1048]
    ...


@lru_cache(maxsize=1)
def _agents_list_cached():
    # [exact body from app/queries.py L516-522]
    ...


def agents_list():
    # [exact body from app/queries.py L524-527]
    ...


@lru_cache(maxsize=1)
def _brands_list_cached():
    # [exact body from app/queries.py L529-533]
    ...


def brands_list():
    # [exact body from app/queries.py L535-537]
    ...
```

**Implementation note:** Copy the exact function bodies from `app/queries.py` — do not rewrite them. The `...` placeholders above indicate where to paste the exact content from the source file.

- [ ] **Step 4.3: Create `app/queries/analytics.py`**

Contains dashboard KPIs, team/agent analytics, and profitability queries. Functions to move (with their exact line ranges from `app/queries.py`):

| Function | Lines |
|---|---|
| `kpi_cards` | 119–163 |
| `kpi_luna_curenta` | 164–184 |
| `monthly_trend` | 186–194 |
| `brand_mix` | 196–203 |
| `channel_mix` | 205–212 |
| `risk_kaufland` | 214–222 |
| `risk_agent` | 224–232 |
| `churn_clients` | 234–243 |
| `top_clients` | 245–279 |
| `team_table` | 286–332 |
| `agent_kpi` | 334–372 |
| `agent_monthly_trend` | 374–382 |
| `agent_clients` | 384–400 |
| `agent_top_skus` | 402–414 |
| `agent_clients_full` | 1326–1389 |
| `agent_brands_full` | 1391–1453 |
| `agent_skus_full` | 1455–1545 |
| `agent_brand_sku_monthly` | 1547–1597 |
| `agent_monthly_full` | 1599–1653 |
| `agent_monthly_base` | 871–886 |
| `agent_monthly_all_years` | 888–899 |
| `agent_brand_monthly` | 901–914 |
| `profitabilitate_agenti` | 1978–2042 |
| `profitabilitate_clienti` | 2044–2105 |
| `profitabilitate_produse` | 2107–2182 |
| `profitabilitate_matrice` | 2184–2228 |

Header:
```python
# app/queries/analytics.py
from db import query, query_one, get_db
from queries._shared import _years_params, display_years, max_luna_for_year
```

- [ ] **Step 4.4: Create `app/queries/clients.py`**

| Function | Lines |
|---|---|
| `clients_list` | 416–514 |
| `client_info` | 539–553 |
| `client_orders` | 555–566 |
| `client_brand_mix` | 568–576 |
| `client_yearly` | 578–585 |
| `client_products_full` | 1655–1747 |
| `client_yearly_full` | 1749–1781 |
| `client_monthly_full` | 1783–1798 |

Header:
```python
# app/queries/clients.py
from db import query, query_one, get_db
from queries._shared import _years_params, display_years, max_luna_for_year
```

- [ ] **Step 4.5: Create `app/queries/products.py`**

| Function | Lines |
|---|---|
| `products_brands` | 587–653 |
| `products_top_skus` | 655–756 |
| `brand_monthly_full` | 758–771 |
| `brand_kpi` | 773–813 |
| `brand_clients` | 815–860 |
| `product_kpi` | 1800–1862 |
| `product_clients` | 1864–1909 |
| `product_monthly` | 1911–1924 |
| `product_yearly` | 1926–1976 |
| `sku_clients_monthly` | 2554–2590 |

Header:
```python
# app/queries/products.py
from db import query, query_one, get_db
from queries._shared import _years_params, display_years, max_luna_for_year
```

- [ ] **Step 4.6: Create `app/queries/pricing.py`**

| Function | Lines |
|---|---|
| `preturi_catalog` | 916–957 |
| `preturi_sku` | 959–974 |
| `preturi_client_sku` | 976–988 |
| `preturi_update_landing` | 990–1006 |
| `preturi_update_vanzare` | 1008–1017 |
| `preturi_update_produs` | 1019–1027 |
| `rate_schimb_list` | 1029–1033 |
| `rate_schimb_update` | 1035–1041 |
| `conditii_list` | 1049–1073 |
| `conditii_get` | 1075–1078 |
| `conditii_create` | 1080–1090 |
| `conditii_update` | 1092–1101 |
| `conditii_delete` | 1103–1107 |
| `termene_list` | 1109–1126 |
| `termene_create` | 1128–1136 |
| `termene_delete` | 1138–1142 |
| `marja_ajustata` | 1144–1191 |

Header:
```python
# app/queries/pricing.py
from db import query, query_one, get_db
from queries._shared import _years_params, display_years, rebuild_cond_resolved
```

- [ ] **Step 4.7: Create `app/queries/orders.py`**

| Function | Lines |
|---|---|
| `termene_aprovizionare_list` | 2592–2594 |
| `termene_partial_update` | 2596–2613 |
| `termene_aprovizionare_upsert` | 3218–end |
| `comenzi_list` | 2615–2638 |
| `comanda_get` | 2640–2657 |
| `comanda_create` | 2659–2670 |
| `comanda_update` | 2672–2691 |
| `comanda_delete` | 2693–2700 |
| `comanda_line_upsert` | 2702–2740 |
| `comanda_line_update` | 2742–2758 |
| `comanda_line_delete` | 2760–2767 |

Header:
```python
# app/queries/orders.py
from db import query, query_one, get_db
```

- [ ] **Step 4.8: Create `app/queries/forecast.py`**

| Function | Lines |
|---|---|
| `forecast_stoc` | 1193–1241 |
| `forecast_summary` | 1243–1274 |
| `forecast_gama_list` | 1276–1324 |
| `forecast_stoc_brand` | 2230–2308 |
| `forecast_stoc_extended` | 2310–2552 |
| `forecast_brands_list` | 2769–2787 |
| `basilur_monthly_per_brand` | 2789–2802 |
| `basilur_kpi_per_brand` | 2804–2844 |
| `basilur_kpi_total` | 2846–2880 |
| `basilur_stoc_per_brand` | 2882–2900 |
| `basilur_stoc_total` | 2902–2917 |
| `basilur_stoc_detail` | 2919–2943 |
| `basilur_monthly_trend` | 2945–2961 |

Header:
```python
# app/queries/forecast.py
from db import query, query_one, get_db
from queries._shared import _years_params, display_years
```

- [ ] **Step 4.9: Create `app/queries/bonus.py`**

| Function | Lines |
|---|---|
| `bonus_team` | 862–869 |

Header:
```python
# app/queries/bonus.py
from db import query
```

- [ ] **Step 4.10: Create `app/queries/export.py`**

| Function | Lines |
|---|---|
| `get_export_hu_codes` | 2963–2972 |
| `monthly_sales_ro_hu` | 2974–3032 |
| `stoc_ro_hu` | 3034–3070 |
| `in_transit_ro_hu` | 3072–3108 |
| `expirare_list` | 3110–3147 |
| `tari_export_list` | 3149–3151 |
| `tari_export_upsert` | 3153–3169 |
| `tari_export_delete` | 3171–3179 |
| `clienti_export_list` | 3181–3188 |
| `clienti_export_upsert` | 3190–3207 |
| `clienti_export_toggle` | 3209–3216 |

Header:
```python
# app/queries/export.py
from db import query, query_one, get_db
from queries._shared import display_years
```

- [ ] **Step 4.11: Create `app/queries/__init__.py`**

This is the backwards-compat re-export layer. All callers do `import queries; queries.some_fn()` — this file makes that work without changing a single callsite.

```python
# app/queries/__init__.py
# Re-exports every public name from domain submodules.
# Callers: `import queries` then `queries.fn()` — unchanged.

from queries._shared import (
    current_year,
    prior_year,
    display_years,
    max_luna_for_year,
    get_sku_cod_mare_map,
    rebuild_cond_resolved,
    ensure_cond_resolved,
    furnizori_list,
    agents_list,
    brands_list,
)
from queries.analytics import (
    kpi_cards,
    kpi_luna_curenta,
    monthly_trend,
    brand_mix,
    channel_mix,
    risk_kaufland,
    risk_agent,
    churn_clients,
    top_clients,
    team_table,
    agent_kpi,
    agent_monthly_trend,
    agent_clients,
    agent_top_skus,
    agent_clients_full,
    agent_brands_full,
    agent_skus_full,
    agent_brand_sku_monthly,
    agent_monthly_full,
    agent_monthly_base,
    agent_monthly_all_years,
    agent_brand_monthly,
    profitabilitate_agenti,
    profitabilitate_clienti,
    profitabilitate_produse,
    profitabilitate_matrice,
)
from queries.clients import (
    clients_list,
    client_info,
    client_orders,
    client_brand_mix,
    client_yearly,
    client_products_full,
    client_yearly_full,
    client_monthly_full,
)
from queries.products import (
    products_brands,
    products_top_skus,
    brand_monthly_full,
    brand_kpi,
    brand_clients,
    product_kpi,
    product_clients,
    product_monthly,
    product_yearly,
    sku_clients_monthly,
)
from queries.pricing import (
    preturi_catalog,
    preturi_sku,
    preturi_client_sku,
    preturi_update_landing,
    preturi_update_vanzare,
    preturi_update_produs,
    rate_schimb_list,
    rate_schimb_update,
    conditii_list,
    conditii_get,
    conditii_create,
    conditii_update,
    conditii_delete,
    termene_list,
    termene_create,
    termene_delete,
    marja_ajustata,
)
from queries.orders import (
    termene_aprovizionare_list,
    termene_partial_update,
    termene_aprovizionare_upsert,
    comenzi_list,
    comanda_get,
    comanda_create,
    comanda_update,
    comanda_delete,
    comanda_line_upsert,
    comanda_line_update,
    comanda_line_delete,
)
from queries.forecast import (
    forecast_stoc,
    forecast_summary,
    forecast_gama_list,
    forecast_stoc_brand,
    forecast_stoc_extended,
    forecast_brands_list,
    basilur_monthly_per_brand,
    basilur_kpi_per_brand,
    basilur_kpi_total,
    basilur_stoc_per_brand,
    basilur_stoc_total,
    basilur_stoc_detail,
    basilur_monthly_trend,
)
from queries.bonus import (
    bonus_team,
)
from queries.export import (
    get_export_hu_codes,
    monthly_sales_ro_hu,
    stoc_ro_hu,
    in_transit_ro_hu,
    expirare_list,
    tari_export_list,
    tari_export_upsert,
    tari_export_delete,
    clienti_export_list,
    clienti_export_upsert,
    clienti_export_toggle,
)
```

- [ ] **Step 4.12: Delete the original `app/queries.py`**

```powershell
Remove-Item app\queries.py
```

- [ ] **Step 4.13: Run tests — must still pass**

```bash
pytest tests/ -v 2>&1 | tail -10
```
Expected: `66 passed`. If import errors occur: check that `app/queries/__init__.py` exports the missing name. If logic errors occur: check that the function body was copied exactly.

- [ ] **Step 4.14: Lint**

```bash
ruff check .
```
Expected: no output. If `F401` (unused import) fires in `__init__.py`: ruff may flag re-exports. Add `# noqa: F401` to the relevant lines or add an `__all__` list.

- [ ] **Step 4.15: Commit**

```
git add app/queries/
git rm app/queries.py
git commit -m "refactor: split queries.py (3236 lines) into domain package — no callsite changes"
```

---

## Task 5: Update CHANGELOG and STATUS

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/STATUS.md`

- [ ] **Step 5.1: Add entry to CHANGELOG.md**

Add a new section at the top of `CHANGELOG.md`:

```markdown
## [0.5.0] - 2026-06-04

### Technical Debt — Phases 1, 2, 3

- Deleted `etl/init_forecast_tables.py` (dead code — broken DB path, schema superseded by migrations 0001 + 0004)
- Updated default AI model in `app/config.py` from retired `claude-opus-4-7` to `claude-sonnet-4-6`
- CI/CD: added explicit `python migrations/runner.py data/torb.db` step before `systemctl restart` — failed migrations now abort deploy rather than crashing the running app
- Tests: replaced 289-line hand-maintained schema in `tests/conftest.py` with `migrations.runner.run_all()` — test schema is always in sync with production schema automatically
- Refactored `app/queries.py` (3,236 lines) into `app/queries/` package with 9 domain modules; `__init__.py` re-exports all names — zero callsite changes required
```

- [ ] **Step 5.2: Update `docs/STATUS.md`**

In the "Livrări recente" section, add at the top:

```markdown
- **2026-06-04 — Technical debt phases 1–3 livrate.**
  Dead code eliminat (`etl/init_forecast_tables.py`, `app/db_stock.py`, `data/stock.db`, `clienti_export_old`). `app/queries.py` (3,236 linii) divizat în pachet `app/queries/` cu 9 module de domeniu. `tests/conftest.py` conectat la migration runner. CI/CD hardened cu pas explicit de migrare înainte de restart. Model AI actualizat la `claude-sonnet-4-6`.
```

- [ ] **Step 5.3: Commit**

```
git add CHANGELOG.md docs/STATUS.md
git commit -m "docs: update CHANGELOG and STATUS for technical debt phases 1-3"
```
