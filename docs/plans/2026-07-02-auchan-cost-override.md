# Business Constants + Auchan True-Cost Override Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize the Auchan/Tobra hard-coded business values into `app/business_constants.py`, and override `pret_cumparare` on imported Auchan rows with Torb's true acquisition cost (30-day simple average from a new `vanzari_tobra` cost table).

**Architecture:** Torb→Tobra invoice lines (cod_client=719), currently thrown away by `etl/import_vanzari_erp.py`, are diverted into a new `vanzari_tobra` table (migration 0013). `etl/import_vanzari_tobra_auchan.py` then overrides each imported row's cost via a fallback chain (30-day window average → last known cost ≤ row date → Excel value) and recomputes `val_achizitie`/`marja_bruta`. Both scripts read shared constants from `app/business_constants.py`.

**Tech Stack:** Python 3, sqlite3, xlrd/openpyxl, pytest, ruff. No new dependencies.

**Spec:** `docs/specs/2026-07-02-auchan-cost-override-design.md` (gitignored, local only).

## Global Constraints

- Work on branch `feat/auchan-cost-override` (create from `main` before Task 1).
- All commands run from project root `c:\MINE\TorbApp`. ETL scripts assume CWD = project root.
- `ruff check .` must pass with zero errors before every commit. Forbidden: E401, E402 (exception: `# noqa: E402` after a `sys.path.insert` — existing precedent at `migrations/runner.py:93`), E701/E702, E722, E741, F401, F841.
- **Encoding rule (critical):** never use the Edit tool to write Romanian text with diacritics into `.py` files (curly-quote/mojibake corruption — see `docs/TECHNICAL.md` §Encoding). Therefore: (a) ALL new strings/comments added to `.py` files in this plan are ASCII-only (`->` not `→`, `randuri` not `rânduri`); (b) when an Edit's `old_string` would contain non-ASCII bytes, use the provided Bash python-replacement script instead. New standalone `.py` files created with the Write tool are ASCII-only too.
- English for code/comments/commits; Romanian only for UI strings and `.md` status entries (diacritics allowed in `.md`/`.html`).
- Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Test-file convention: load ETL modules via `importlib.util.spec_from_file_location` (see `tests/test_derive_furnizor.py`).

---

### Task 1: `app/business_constants.py`

**Files:**
- Create: `app/business_constants.py`
- Test: `tests/test_business_constants.py`

**Interfaces:**
- Produces (used by Tasks 2, 4, 5): module `app/business_constants.py` with constants
  `AUCHAN_COD_CLIENT: str = "732"`, `AUCHAN_CLIENT_NAME: str = "AUCHAN ROMANIA SA"`,
  `AUCHAN_TIP_CLIENT: str = "HYPERMARKET"`, `AUCHAN_AGENT: str = "Oana Filip"`,
  `TOBRA_COD_CLIENT: str = "719"`, `TOBRA_INVOICE_PREFIX: str = "TOBRA"`,
  `TOBRA_COST_WINDOW_DAYS: int = 30`.
- **Import convention (binding):** consumers insert `<project_root>/app` on
  `sys.path` and import FLAT — `from business_constants import ...` — the
  `migrations/runner.py:92-93` pattern. NEVER import it as
  `app.business_constants` and never add `app/__init__.py`: bare `import app`
  must keep resolving to the module `app/app.py` (tests/conftest.py and the
  launcher depend on that; a package named `app` breaks 51 fixture-based tests).

- [ ] **Step 0: Create the branch**

```bash
git checkout -b feat/auchan-cost-override
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_business_constants.py` (flat import — conftest puts `app/` on sys.path):

```python
from business_constants import (
    AUCHAN_AGENT,
    AUCHAN_CLIENT_NAME,
    AUCHAN_COD_CLIENT,
    AUCHAN_TIP_CLIENT,
    TOBRA_COD_CLIENT,
    TOBRA_COST_WINDOW_DAYS,
    TOBRA_INVOICE_PREFIX,
)


def test_auchan_tobra_values():
    assert AUCHAN_COD_CLIENT == "732"
    assert AUCHAN_CLIENT_NAME == "AUCHAN ROMANIA SA"
    assert AUCHAN_TIP_CLIENT == "HYPERMARKET"
    assert AUCHAN_AGENT == "Oana Filip"
    assert TOBRA_COD_CLIENT == "719"
    assert TOBRA_INVOICE_PREFIX == "TOBRA"
    assert TOBRA_COST_WINDOW_DAYS == 30


def test_client_codes_are_strings():
    # tranzactii.cod_client is TEXT — int constants would silently break queries
    assert isinstance(AUCHAN_COD_CLIENT, str)
    assert isinstance(TOBRA_COD_CLIENT, str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_business_constants.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'business_constants'`

- [ ] **Step 3: Write the module**

Create `app/business_constants.py`:

```python
"""Business constants shared across app/ and etl/.

Home for hard-coded business facts (client codes, agent names, business
rule parameters). NOT for deployment/env settings — those live in
app/config.py (env-overridable; business facts must never be).

Convention: each constant group carries a 'Used by:' comment listing the
modules that import it. Update the list when you add a consumer, so
usage is visible here without searching the codebase.
"""

# --- Auchan / Tobra invoicing exception ------------------------------------
# Torb->Auchan sales are invoiced through the intermediary Tobra Invest SRL.
# The ERP import diverts Torb->Tobra lines (cod 719) to the vanzari_tobra
# cost table; the Auchan import injects Tobra->Auchan invoices as Torb sales
# (client 732, agent Oana Filip) and overrides pret_cumparare with the true
# Torb cost averaged over TOBRA_COST_WINDOW_DAYS. Details:
# docs/BUSINESS_LOGIC.md section 3.
#
# Used by:
#   etl/import_vanzari_tobra_auchan.py
#   etl/import_vanzari_erp.py
AUCHAN_COD_CLIENT = "732"
AUCHAN_CLIENT_NAME = "AUCHAN ROMANIA SA"
AUCHAN_TIP_CLIENT = "HYPERMARKET"
AUCHAN_AGENT = "Oana Filip"

TOBRA_COD_CLIENT = "719"
TOBRA_INVOICE_PREFIX = "TOBRA"
TOBRA_COST_WINDOW_DAYS = 30
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_business_constants.py -v`
Expected: 2 passed

- [ ] **Step 5: Lint and commit**

Run: `ruff check .` — expected: no errors.

```bash
git add app/business_constants.py tests/test_business_constants.py
git commit -m "feat: add app/business_constants.py for shared business facts

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Rewire `etl/import_vanzari_tobra_auchan.py` to the constants

**Files:**
- Modify: `etl/import_vanzari_tobra_auchan.py` (constants block at lines 30–39, usages at lines 146, 229–236, 301–313)

**Interfaces:**
- Consumes: constants from `app/business_constants.py` (Task 1, flat import per its binding convention).
- Produces: no new API — same module behavior, constants now imported. `TOBRA_COD_CLIENT` keeps its name (now imported); `AGENT_OVERRIDE→AUCHAN_AGENT`, `COD_CLIENT_OVERRIDE→AUCHAN_COD_CLIENT`, `CLIENT_OVERRIDE→AUCHAN_CLIENT_NAME`, `TIP_CLIENT_OVERRIDE→AUCHAN_TIP_CLIENT`.

- [ ] **Step 1: Add the import (Edit tool — ASCII-safe)**

In `etl/import_vanzari_tobra_auchan.py`, replace:

```python
import xlrd

if sys.platform == "win32":
```

with:

```python
import xlrd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from business_constants import (  # noqa: E402
    AUCHAN_AGENT,
    AUCHAN_CLIENT_NAME,
    AUCHAN_COD_CLIENT,
    AUCHAN_TIP_CLIENT,
    TOBRA_COD_CLIENT,
    TOBRA_INVOICE_PREFIX,
)

if sys.platform == "win32":
```

- [ ] **Step 2: Remove the local constants block (Bash script — block contains non-ASCII)**

The block from `# Hard-coded overrides` through `TOBRA_COD_CLIENT     = "719"` (lines 30–39) contains em-dashes/diacritics, so remove it via Bash:

```bash
python -c "
p = 'etl/import_vanzari_tobra_auchan.py'
with open(p, encoding='utf-8') as f:
    c = f.read()
start = c.index('# Hard-coded overrides')
end = c.index('TOBRA_COD_CLIENT     = \"719\"')
end = c.index('\n', end) + 1
c = c[:start] + c[end:]
while '\n\n\n\n' in c:
    c = c.replace('\n\n\n\n', '\n\n\n')
with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('removed')
"
```

- [ ] **Step 3: Rename usages (Edit tool, replace_all, IN THIS ORDER)**

Order matters — `TIP_CLIENT_OVERRIDE` and `COD_CLIENT_OVERRIDE` contain the substring `CLIENT_OVERRIDE`:

1. `TIP_CLIENT_OVERRIDE` → `AUCHAN_TIP_CLIENT` (replace_all)
2. `COD_CLIENT_OVERRIDE` → `AUCHAN_COD_CLIENT` (replace_all)
3. `CLIENT_OVERRIDE` → `AUCHAN_CLIENT_NAME` (replace_all)
4. `AGENT_OVERRIDE` → `AUCHAN_AGENT` (replace_all)

- [ ] **Step 4: Replace the inline literals in the summary queries (Edit tool — ASCII)**

Replace:

```python
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*), SUM(val_neta), MIN(data_dl), MAX(data_dl)
        FROM tranzactii WHERE nr_factura LIKE 'TOBRA%'
    """)
```

with:

```python
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*), SUM(val_neta), MIN(data_dl), MAX(data_dl)"
        " FROM tranzactii WHERE nr_factura LIKE ?",
        (TOBRA_INVOICE_PREFIX + "%",),
    )
```

Replace:

```python
    cur.execute("""
        SELECT COUNT(*), SUM(val_neta) FROM tranzactii
        WHERE cod_client='732' AND agent=? AND nr_factura LIKE 'TOBRA%'
    """, (AUCHAN_AGENT,))
```

with:

```python
    cur.execute(
        "SELECT COUNT(*), SUM(val_neta) FROM tranzactii"
        " WHERE cod_client=? AND agent=? AND nr_factura LIKE ?",
        (AUCHAN_COD_CLIENT, AUCHAN_AGENT, TOBRA_INVOICE_PREFIX + "%"),
    )
```

(If Step 3's rename already changed `(AGENT_OVERRIDE,)` to `(AUCHAN_AGENT,)`, match that.)

Also replace docstring line 10 (ASCII → ASCII):

```
Suprascrieri:    agent='Oana Filip', cod_client='732', client='AUCHAN ROMANIA SA'
```

with:

```
Suprascrieri:    vezi app/business_constants.py (AUCHAN_*, TOBRA_*)
```

- [ ] **Step 5: Verify — module loads, tests pass, lint clean**

Run: `python -c "import importlib.util; s=importlib.util.spec_from_file_location('m','etl/import_vanzari_tobra_auchan.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.AUCHAN_AGENT, m.TOBRA_COD_CLIENT)"`
Expected: `Oana Filip 719`

Run: `python -m pytest tests/ -q` — expected: all pass (existing `test_derive_furnizor.py` loads this module).
Run: `ruff check .` — expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add etl/import_vanzari_tobra_auchan.py
git commit -m "refactor: auchan import reads overrides from business_constants

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Migration 0013 — `vanzari_tobra` table (+ rebuild_db)

**Files:**
- Create: `migrations/0013_20260702_vanzari_tobra.py`
- Modify: `etl/rebuild_db.py` (after the `CREATE_TABLE` constant ends at line 67; inside `reset_tranzactii` at line 210)
- Test: `tests/test_vanzari_tobra.py` (created here, extended in Task 4)

**Interfaces:**
- Produces: table `vanzari_tobra(id, data_dl TEXT, nr_dl TEXT, nr_factura TEXT, cod_produs TEXT, sku TEXT, cantitate REAL, pret_cumparare REAL, pret_vanzare REAL, UNIQUE(nr_dl, cod_produs, nr_factura, pret_vanzare))` + index `idx_vanzari_tobra_cod_data(cod_produs, data_dl)`. Also `rebuild_db.CREATE_VANZARI_TOBRA` / `rebuild_db.VANZARI_TOBRA_INDEX` module constants.

- [ ] **Step 1: Write the failing test**

Create `tests/test_vanzari_tobra.py`:

```python
import importlib.util
import os
import sqlite3

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _migration_0013():
    return _load(
        os.path.join(ROOT, "migrations", "0013_20260702_vanzari_tobra.py"),
        "_migration_0013",
    )


EXPECTED_COLS = {
    "id", "data_dl", "nr_dl", "nr_factura", "cod_produs", "sku",
    "cantitate", "pret_cumparare", "pret_vanzare",
}


def test_migration_0013_creates_table_and_is_idempotent():
    conn = sqlite3.connect(":memory:")
    mig = _migration_0013()
    assert mig.VERSION == 13
    mig.up(conn)
    mig.up(conn)  # IF NOT EXISTS — safe to re-apply
    cols = {r[1] for r in conn.execute("PRAGMA table_info(vanzari_tobra)")}
    assert cols == EXPECTED_COLS
    idx = {r[1] for r in conn.execute("PRAGMA index_list(vanzari_tobra)")}
    assert "idx_vanzari_tobra_cod_data" in idx


def test_rebuild_db_schema_matches_migration():
    rebuild = _load(os.path.join(ROOT, "etl", "rebuild_db.py"), "_rebuild_db")
    conn = sqlite3.connect(":memory:")
    conn.execute(rebuild.CREATE_VANZARI_TOBRA)
    conn.execute(rebuild.VANZARI_TOBRA_INDEX)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(vanzari_tobra)")}
    assert cols == EXPECTED_COLS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_vanzari_tobra.py -v`
Expected: FAIL — `FileNotFoundError` for the migration file.

- [ ] **Step 3: Write the migration**

Create `migrations/0013_20260702_vanzari_tobra.py`:

```python
"""
Migration 0013 -- vanzari_tobra cost table.

Torb->Tobra invoice lines (cod_client=719) are diverted here by
etl/import_vanzari_erp.py instead of being dropped. Holds Torb's true
acquisition cost per product over time; consumed by
etl/import_vanzari_tobra_auchan.py to override pret_cumparare on
imported Tobra->Auchan rows. Idempotent.
"""

VERSION = 13
NAME = "0013_20260702_vanzari_tobra"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vanzari_tobra (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            data_dl        TEXT,
            nr_dl          TEXT,
            nr_factura     TEXT,
            cod_produs     TEXT,
            sku            TEXT,
            cantitate      REAL,
            pret_cumparare REAL,
            pret_vanzare   REAL,
            UNIQUE(nr_dl, cod_produs, nr_factura, pret_vanzare)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vanzari_tobra_cod_data"
        " ON vanzari_tobra(cod_produs, data_dl)"
    )
```

- [ ] **Step 4: Add the table to `etl/rebuild_db.py`**

Insert after the closing `"""` of `CREATE_TABLE` (before `INDEXES = [`), via Edit tool (ASCII anchor `INDEXES = [`):

```python
# Cost table for the Auchan import (migration 0013). NOT dropped on rebuild:
# cost history persists; INSERT OR IGNORE in import_vanzari_erp.py dedups.
CREATE_VANZARI_TOBRA = """
CREATE TABLE IF NOT EXISTS vanzari_tobra (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    data_dl        TEXT,
    nr_dl          TEXT,
    nr_factura     TEXT,
    cod_produs     TEXT,
    sku            TEXT,
    cantitate      REAL,
    pret_cumparare REAL,
    pret_vanzare   REAL,
    UNIQUE(nr_dl, cod_produs, nr_factura, pret_vanzare)
)
"""

VANZARI_TOBRA_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_vanzari_tobra_cod_data"
    " ON vanzari_tobra(cod_produs, data_dl)"
)

INDEXES = [
```

In `reset_tranzactii`, replace (ASCII anchor):

```python
    conn.execute(CREATE_TABLE)
    for idx in INDEXES:
```

with:

```python
    conn.execute(CREATE_TABLE)
    conn.execute(CREATE_VANZARI_TOBRA)
    conn.execute(VANZARI_TOBRA_INDEX)
    for idx in INDEXES:
```

Rebuild ordering note (already correct, no change needed): `rebuild_db.main()` runs `import_vanzari_erp` at step [3] (populates `vanzari_tobra`) before `import_vanzari_tobra_auchan` at step [4] (consumes it) — a full rebuild applies the cost rule to all history.

- [ ] **Step 5: Run tests, lint**

Run: `python -m pytest tests/test_vanzari_tobra.py -v` — expected: 2 passed.
Run: `ruff check .` — expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add migrations/0013_20260702_vanzari_tobra.py etl/rebuild_db.py tests/test_vanzari_tobra.py
git commit -m "feat: add vanzari_tobra cost table (migration 0013)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: ERP import diverts Torb→Tobra rows into `vanzari_tobra`

**Files:**
- Modify: `etl/import_vanzari_erp.py` (imports at lines 13–22; `SKIP_COD_CLIENT` block at lines 33–37; `process_rows` at lines 221–317; `run()` at lines 384–410)
- Test: `tests/test_vanzari_tobra.py` (extend)

**Interfaces:**
- Consumes: `TOBRA_COD_CLIENT` from `app/business_constants.py` (Task 1, flat import); table `vanzari_tobra` (Task 3).
- Produces: `process_rows(rows_raw, cp_lookup) -> tuple[list[dict], list[dict]]` (was `-> list[dict]`); `insert_tobra_rows(conn, tobra_records) -> int`; module constant `TOBRA_COLS: list[str]`. Tobra record dict keys = `TOBRA_COLS` = `["data_dl", "nr_dl", "nr_factura", "cod_produs", "sku", "cantitate", "pret_cumparare", "pret_vanzare"]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vanzari_tobra.py`:

```python
from datetime import datetime


def _erp():
    return _load(os.path.join(ROOT, "etl", "import_vanzari_erp.py"), "_erp_mod")


def _erp_raw_row(codcli, nrdl, codprod, pcump):
    return {
        "codcli": codcli, "datadl": datetime(2026, 6, 15), "nrdl": nrdl,
        "factout": "F1", "nrcomandam": None, "codprod": codprod,
        "den_b": "B.TEST TEA", "um": "BUC", "cantit": 5, "pvanz": 6.0,
        "tva": 9.0, "pcump": pcump, "discount": 0, "procent": 0,
        "den_a": "CLIENT X", "numeag": "AGENT X", "adresa": None,
        "locatie": None, "numetipcli": None, "cfcli": None,
        "localcli": None, "judet": None, "adr_livr": None,
    }


def test_process_rows_diverts_tobra_lines():
    erp = _erp()
    rows = [
        _erp_raw_row(719.0, "DL1", "100", 3.5),   # Torb->Tobra: diverted
        _erp_raw_row(100, "DL2", "200", 1.0),     # normal client: kept
    ]
    records, tobra = erp.process_rows(rows, {})
    assert len(records) == 1
    assert records[0]["cod_client"] == 100
    assert len(tobra) == 1
    t = tobra[0]
    assert t["data_dl"] == "2026-06-15"
    assert t["nr_dl"] == "DL1"
    assert t["cod_produs"] == "100"
    assert t["pret_cumparare"] == 3.5
    assert t["pret_vanzare"] == 6.0
    assert t["cantitate"] == 5.0


def test_insert_tobra_rows_is_idempotent():
    erp = _erp()
    conn = sqlite3.connect(":memory:")
    _migration_0013().up(conn)
    rec = {"data_dl": "2026-06-15", "nr_dl": "DL1", "nr_factura": "F1",
           "cod_produs": "100", "sku": "B.TEST TEA", "cantitate": 5.0,
           "pret_cumparare": 3.5, "pret_vanzare": 6.0}
    assert erp.insert_tobra_rows(conn, [rec]) == 1
    assert erp.insert_tobra_rows(conn, [rec]) == 0
    assert conn.execute("SELECT COUNT(*) FROM vanzari_tobra").fetchone()[0] == 1
    assert erp.insert_tobra_rows(conn, []) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vanzari_tobra.py -v`
Expected: the two new tests FAIL (`too many values to unpack` / `has no attribute 'insert_tobra_rows'`); Task 3 tests still pass.

- [ ] **Step 3: Add the constants import (Edit tool — ASCII)**

In `etl/import_vanzari_erp.py`, replace:

```python
from datetime import datetime, date

if sys.platform == "win32":
```

with:

```python
from datetime import datetime, date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from business_constants import TOBRA_COD_CLIENT  # noqa: E402

if sys.platform == "win32":
```

- [ ] **Step 4: Replace the SKIP block (Bash script — block contains non-ASCII)**

```bash
python -c "
p = 'etl/import_vanzari_erp.py'
with open(p, encoding='utf-8') as f:
    c = f.read()
start = c.index('# Cod-uri client de excluse')
end = c.index('SKIP_COD_CLIENT = {\"719\"}')
end = c.index('\n', end) + 1
new = '''# Torb->Tobra invoice lines (cod_client=TOBRA_COD_CLIENT) are diverted to
# the vanzari_tobra cost table (true Torb acquisition cost per product),
# consumed by import_vanzari_tobra_auchan.py. They never enter tranzactii.
TOBRA_COLS = [
    \"data_dl\", \"nr_dl\", \"nr_factura\", \"cod_produs\", \"sku\",
    \"cantitate\", \"pret_cumparare\", \"pret_vanzare\",
]
'''
c = c[:start] + new + c[end:]
with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('replaced')
"
```

- [ ] **Step 5: Divert in `process_rows` (Bash script — old block contains diacritics)**

```bash
python -c "
p = 'etl/import_vanzari_erp.py'
with open(p, encoding='utf-8') as f:
    c = f.read()
start = c.index('def process_rows(rows_raw, cp_lookup):')
end = c.index('# Map ERP column names to canonical names')
new = '''def _tobra_record(raw):
    return {
        \"data_dl\": normalize_date(raw.get(\"datadl\")),
        \"nr_dl\": normalize_str(raw.get(\"nrdl\")),
        \"nr_factura\": normalize_str(raw.get(\"factout\")),
        \"cod_produs\": normalize_str(raw.get(\"codprod\")),
        \"sku\": normalize_str(raw.get(\"den_b\")),
        \"cantitate\": normalize_num(raw.get(\"cantit\")),
        \"pret_cumparare\": normalize_num(raw.get(\"pcump\")),
        \"pret_vanzare\": normalize_num(raw.get(\"pvanz\")),
    }


def process_rows(rows_raw, cp_lookup):
    records = []
    tobra_records = []
    for raw in rows_raw:
        # Divert Torb->Tobra lines to the cost table instead of tranzactii
        cod_cli_raw = raw.get(\"codcli\")
        if cod_cli_raw is not None:
            try:
                cod_cli_str = str(int(float(cod_cli_raw)))
            except (ValueError, TypeError):
                cod_cli_str = str(cod_cli_raw).strip()
            if cod_cli_str == TOBRA_COD_CLIENT:
                tobra_records.append(_tobra_record(raw))
                continue

        '''
c = c[:start] + new + c[end:]
with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('replaced')
"
```

Then replace the end of `process_rows` (Bash script — old text contains diacritics):

```bash
python -c "
p = 'etl/import_vanzari_erp.py'
with open(p, encoding='utf-8') as f:
    c = f.read()
start = c.index('    if skipped_intermediary:')
end = c.index('    return records\n', start) + len('    return records\n')
new = '''    if tobra_records:
        print(f\"    -> Deviate in vanzari_tobra: {len(tobra_records):,} randuri (cod_client={TOBRA_COD_CLIENT})\")
    return records, tobra_records
'''
c = c[:start] + new + c[end:]
with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('replaced')
"
```

Note: `skipped_intermediary` no longer exists after this step — the two Bash scripts above remove both its initialization (Step 5 first script rewrites the function head without it) and its final print. Verify with: `grep -c skipped_intermediary etl/import_vanzari_erp.py` → expected `0`.

- [ ] **Step 6: Add `insert_tobra_rows` and wire `run()` (Edit tool — ASCII anchors)**

Insert before `def run(filepath=None):`:

```python
def insert_tobra_rows(conn, tobra_records):
    if not tobra_records:
        return 0
    placeholders = ", ".join(["?" for _ in TOBRA_COLS])
    cols = ", ".join(TOBRA_COLS)
    sql = f"INSERT OR IGNORE INTO vanzari_tobra ({cols}) VALUES ({placeholders})"
    data = [[r[c] for c in TOBRA_COLS] for r in tobra_records]
    cursor = conn.cursor()
    cursor.executemany(sql, data)
    conn.commit()
    return cursor.rowcount


def run(filepath=None):
```

In `run()`, replace:

```python
    records = process_rows(rows_raw, cp_lookup)
```

with:

```python
    records, tobra_records = process_rows(rows_raw, cp_lookup)
```

And replace (unique ASCII anchor):

```python
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), MIN(data_dl), MAX(data_dl) FROM tranzactii")
```

with:

```python
    n_tobra = insert_tobra_rows(conn, tobra_records)
    if tobra_records:
        print(f"    -> Inserate in vanzari_tobra: {n_tobra:,} | Duplicate ignorate: {len(tobra_records) - n_tobra:,}")

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), MIN(data_dl), MAX(data_dl) FROM tranzactii")
```

(Upload row-count note: `app/blueprints/forecast.py` parses stdout with `r'([\d,]+)\s*rânduri'` and `r'Inserate:\s*([\d,]+)'`. The new ASCII prints — `randuri` without â, `Inserate in vanzari_tobra:` without a direct colon after `Inserate` — deliberately do NOT match either pattern, so the UI row count is unaffected.)

- [ ] **Step 7: Run tests, lint**

Run: `python -m pytest tests/ -q` — expected: all pass.
Run: `ruff check .` — expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add etl/import_vanzari_erp.py tests/test_vanzari_tobra.py
git commit -m "feat: ERP import diverts Torb->Tobra lines into vanzari_tobra

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Cost override in the Auchan import

**Files:**
- Modify: `etl/import_vanzari_tobra_auchan.py`
- Test: `tests/test_auchan_cost_override.py`

**Interfaces:**
- Consumes: `vanzari_tobra` table (Task 3); `TOBRA_COST_WINDOW_DAYS` (Task 1); Task 2's import block.
- Produces: `lookup_tobra_cost(conn, cod_produs, data_dl_str) -> tuple[float | None, str | None]` (source: `"window"` / `"last_known"` / `None`); `apply_cost_override(conn, records) -> dict` (counts keyed `"window"`, `"last_known"`, `"excel"`; mutates records in place).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auchan_cost_override.py`:

```python
import importlib.util
import os
import sqlite3

ETL = os.path.join(os.path.dirname(__file__), "..", "etl")


def _mod():
    path = os.path.join(ETL, "import_vanzari_tobra_auchan.py")
    spec = importlib.util.spec_from_file_location("_auchan_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _conn(cost_rows):
    """cost_rows: list of (data_dl, cod_produs, pret_cumparare)."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE vanzari_tobra ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " data_dl TEXT, nr_dl TEXT, nr_factura TEXT,"
        " cod_produs TEXT, sku TEXT,"
        " cantitate REAL, pret_cumparare REAL, pret_vanzare REAL,"
        " UNIQUE(nr_dl, cod_produs, nr_factura, pret_vanzare))"
    )
    conn.executemany(
        "INSERT INTO vanzari_tobra (data_dl, nr_dl, cod_produs, pret_cumparare)"
        " VALUES (?, ?, ?, ?)",
        [(d, f"DL{i}", cod, p) for i, (d, cod, p) in enumerate(cost_rows)],
    )
    return conn


def _record(**kw):
    rec = {"cod_produs": "100", "data_dl": "2026-06-25", "cantitate": 10.0,
           "pret_cumparare": 3.0, "val_neta": 100.0,
           "val_achizitie": 30.0, "marja_bruta": 70.0}
    rec.update(kw)
    return rec


def test_window_average_is_simple_average():
    m = _mod()
    conn = _conn([("2026-06-10", "100", 5.0), ("2026-06-20", "100", 7.0)])
    assert m.lookup_tobra_cost(conn, "100", "2026-06-25") == (6.0, "window")


def test_window_includes_same_day():
    m = _mod()
    conn = _conn([("2026-07-02", "100", 4.0)])
    assert m.lookup_tobra_cost(conn, "100", "2026-07-02") == (4.0, "window")


def test_entry_exactly_30_days_old_falls_to_last_known():
    m = _mod()
    # window is (d-30, d]: 2026-06-02 == d-30 for d=2026-07-02 -> excluded
    conn = _conn([("2026-06-02", "100", 5.0)])
    assert m.lookup_tobra_cost(conn, "100", "2026-07-02") == (5.0, "last_known")


def test_last_known_averages_the_most_recent_day_only():
    m = _mod()
    conn = _conn([("2026-01-15", "100", 5.0), ("2026-01-15", "100", 6.0),
                  ("2026-01-01", "100", 9.0)])
    assert m.lookup_tobra_cost(conn, "100", "2026-06-25") == (5.5, "last_known")


def test_future_entries_are_ignored():
    m = _mod()
    conn = _conn([("2026-07-10", "100", 9.9)])
    assert m.lookup_tobra_cost(conn, "100", "2026-07-02") == (None, None)


def test_unknown_product_returns_none():
    m = _mod()
    conn = _conn([])
    assert m.lookup_tobra_cost(conn, "999", "2026-07-02") == (None, None)


def test_apply_override_recomputes_financials():
    m = _mod()
    conn = _conn([("2026-06-20", "100", 2.5)])
    rec = _record()
    counts = m.apply_cost_override(conn, [rec])
    assert rec["pret_cumparare"] == 2.5
    assert rec["val_achizitie"] == 25.0
    assert rec["marja_bruta"] == 75.0
    assert counts == {"window": 1, "last_known": 0, "excel": 0}


def test_apply_override_keeps_excel_value_without_data():
    m = _mod()
    conn = _conn([])
    rec = _record()
    counts = m.apply_cost_override(conn, [rec])
    assert rec["pret_cumparare"] == 3.0
    assert rec["val_achizitie"] == 30.0
    assert rec["marja_bruta"] == 70.0
    assert counts == {"window": 0, "last_known": 0, "excel": 1}


def test_apply_override_missing_cod_produs_uses_excel():
    m = _mod()
    conn = _conn([("2026-06-20", "100", 2.5)])
    rec = _record(cod_produs=None)
    counts = m.apply_cost_override(conn, [rec])
    assert rec["pret_cumparare"] == 3.0
    assert counts == {"window": 0, "last_known": 0, "excel": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_auchan_cost_override.py -v`
Expected: FAIL — `has no attribute 'lookup_tobra_cost'`.

- [ ] **Step 3: Implement (Edit tool — ASCII anchors and content)**

In `etl/import_vanzari_tobra_auchan.py`:

3a. Add to the imports — replace:

```python
import xlrd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

with:

```python
import xlrd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

3b. Extend the constants import — replace (this two-line form is unique; bare `TOBRA_COD_CLIENT,` is NOT — it also appears in `(TOBRA_COD_CLIENT,)` tuples):

```python
    AUCHAN_TIP_CLIENT,
    TOBRA_COD_CLIENT,
```

with:

```python
    AUCHAN_TIP_CLIENT,
    TOBRA_COD_CLIENT,
    TOBRA_COST_WINDOW_DAYS,
```

3c. Insert before `def build_cod_furnizor_lookup(conn):`:

```python
def lookup_tobra_cost(conn, cod_produs, data_dl_str):
    """True Torb acquisition cost for cod_produs at date data_dl_str.

    Returns (cost, source): "window" = simple avg over the last
    TOBRA_COST_WINDOW_DAYS days (exclusive start, inclusive end);
    "last_known" = avg of entries on the most recent data_dl <= date.
    (None, None) when vanzari_tobra has no usable entry.
    """
    d = datetime.strptime(data_dl_str, "%Y-%m-%d").date()
    window_start = (d - timedelta(days=TOBRA_COST_WINDOW_DAYS)).strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute(
        "SELECT AVG(pret_cumparare) FROM vanzari_tobra"
        " WHERE cod_produs = ? AND pret_cumparare IS NOT NULL"
        " AND data_dl > ? AND data_dl <= ?",
        (cod_produs, window_start, data_dl_str),
    )
    avg = cur.fetchone()[0]
    if avg is not None:
        return round(avg, 4), "window"
    cur.execute(
        "SELECT AVG(pret_cumparare) FROM vanzari_tobra"
        " WHERE cod_produs = ? AND pret_cumparare IS NOT NULL"
        " AND data_dl = (SELECT MAX(data_dl) FROM vanzari_tobra"
        "  WHERE cod_produs = ? AND pret_cumparare IS NOT NULL"
        "  AND data_dl <= ?)",
        (cod_produs, cod_produs, data_dl_str),
    )
    last = cur.fetchone()[0]
    if last is not None:
        return round(last, 4), "last_known"
    return None, None


def apply_cost_override(conn, records):
    """Override pret_cumparare with the true Torb cost from vanzari_tobra
    and recompute val_achizitie + marja_bruta. Rows without a known cost
    keep the value from the Tobra file. Mutates records; returns counts."""
    cache = {}
    counts = {"window": 0, "last_known": 0, "excel": 0}
    for r in records:
        cod = r["cod_produs"]
        if not cod:
            counts["excel"] += 1
            continue
        key = (cod, r["data_dl"])
        if key not in cache:
            cache[key] = lookup_tobra_cost(conn, cod, r["data_dl"])
        cost, source = cache[key]
        if cost is None:
            counts["excel"] += 1
            continue
        counts[source] += 1
        r["pret_cumparare"] = cost
        r["val_achizitie"] = round((r["cantitate"] or 0) * cost, 4)
        r["marja_bruta"] = round((r["val_neta"] or 0) - r["val_achizitie"], 4)
    print(f"    -> Cost real Torb: {counts['window']:,} medie {TOBRA_COST_WINDOW_DAYS}z"
          f" | {counts['last_known']:,} ultimul cost | {counts['excel']:,} valoare fisier")
    return counts


def build_cod_furnizor_lookup(conn):
```

3d. Wire into `run()` — replace:

```python
    inserted = insert_rows(conn, records)
```

with:

```python
    apply_cost_override(conn, records)

    inserted = insert_rows(conn, records)
```

- [ ] **Step 4: Run tests, lint**

Run: `python -m pytest tests/ -q` — expected: all pass.
Run: `ruff check .` — expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add etl/import_vanzari_tobra_auchan.py tests/test_auchan_cost_override.py
git commit -m "feat: override Auchan pret_cumparare with true Torb cost

30-day simple average from vanzari_tobra per cod_produs at each row's
own date; fallback to last known cost, then the file value.
val_achizitie and marja_bruta recomputed.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: UI hint + documentation updates

**Files:**
- Modify: `app/templates/actualizare.html:46`
- Modify: `docs/BUSINESS_LOGIC.md` (end of §3, before `## 4. Bonus calculation`)
- Modify: `docs/TECHNICAL.md` (§Data, after the `tranzactii` description at line ~12)
- Modify: `context/STATUS.md` (top of `## Livrări recente`, line ~56)

**Interfaces:** none (docs only). Romanian diacritics are fine in `.html`/`.md`.

- [ ] **Step 1: UI hint (Bash script — new text has diacritics)**

```bash
python -c "
p = 'app/templates/actualizare.html'
with open(p, encoding='utf-8') as f:
    c = f.read()
old = '<div class=\"zone-hint text-muted small mb-3\">vz auchan*.xls</div>'
new = '<div class=\"zone-hint text-muted small mb-3\">vz auchan*.xls · încărcați după Vânzări ERP</div>'
assert old in c
c = c.replace(old, new)
with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('done')
"
```

Result on the page: `vz auchan*.xls · încărcați după Vânzări ERP`.

- [ ] **Step 2: BUSINESS_LOGIC.md — add the exception subsection**

Insert immediately before `## 4. Bonus calculation` (keep the `---` separator above it):

```markdown
### The Auchan/Tobra exception

Torb→Auchan sales are invoiced through the intermediary **Tobra Invest SRL**
(cod_client 719 in Torb's ERP). Shared constants: `app/business_constants.py`.

- `etl/import_vanzari_erp.py` diverts Torb→Tobra invoice lines (cod 719) out of
  `tranzactii` into the cost table `vanzari_tobra` — Torb's true acquisition
  cost per product over time.
- `etl/import_vanzari_tobra_auchan.py` imports Tobra→Auchan invoices as if they
  were Torb→Auchan sales (client 732 `AUCHAN ROMANIA SA`, agent Oana Filip;
  invoice numbers keep the `TOBRA` prefix as a marker).
- **Cost rule (2026-07-02):** each imported row's `pret_cumparare` is overridden
  with the simple average of `vanzari_tobra` costs for that `cod_produs` over
  the 30 days before the row's own `data_dl`; fallback: most recent cost ≤ row
  date, then the value from the Tobra file. `val_achizitie` and `marja_bruta`
  are recomputed. Upload order matters: import Vânzări ERP before Vânzări
  Auchan so the cost table is fresh.

---

```

- [ ] **Step 3: TECHNICAL.md §Data — mention the new table**

After the line `Main table: ``tranzactii`` (31 columns). Useful views: ...`, add:

```markdown
Cost table: `vanzari_tobra` — Torb→Tobra invoice lines (true acquisition cost),
diverted at ERP import; consumed by the Auchan-import cost override
(`docs/BUSINESS_LOGIC.md` §3, migration 0013).
```

- [ ] **Step 4: STATUS.md — record the delivery**

Insert as the FIRST entry under `## Livrări recente`:

```markdown
- **2026-07-02 — Constante business centralizate + cost real Torb pe vânzările Auchan.**
  Modul nou `app/business_constants.py` (excepția Auchan/Tobra: agent, coduri client, prefix factură, fereastră cost 30z), folosit de `import_vanzari_erp.py` + `import_vanzari_tobra_auchan.py`. Tabel nou `vanzari_tobra` (migrația 0013): liniile Torb→Tobra (cod 719) sunt deviate acolo la importul ERP în loc să fie aruncate. Importul Auchan suprascrie `pret_cumparare` cu media simplă pe 30 zile per `cod_produs` la data fiecărui rând (fallback: ultimul cost cunoscut, apoi valoarea din fișier) și recalculează `val_achizitie`/`marja_bruta`. Ordine încărcare: Vânzări ERP înainte de Vânzări Auchan (notat în UI). Necesită backfill: un re-import al fișierului ERP de vânzări.
```

- [ ] **Step 5: Commit**

```bash
git add app/templates/actualizare.html docs/BUSINESS_LOGIC.md docs/TECHNICAL.md context/STATUS.md
git commit -m "docs: document vanzari_tobra cost rule + upload-order hint

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Apply migration, backfill, end-to-end verification

**Files:** none (operational — local `data/torb.db`).

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Apply migration 0013 to the local DB**

Run: `python migrations/runner.py`
Expected output includes: `Applying 0013: 0013_20260702_vanzari_tobra ...` then `0013 OK.`

- [ ] **Step 2: Backfill — re-import the ERP sales file**

Only if an ERP export exists (auto-detected in `docs_input/DD.MM.YYYY/vanzari*.xlsx`):

Run: `python etl/import_vanzari_erp.py`
Expected output includes: `-> Deviate in vanzari_tobra: N randuri (cod_client=719)` and `-> Inserate in vanzari_tobra: N | ...` with N > 0.
If no file is present, note it and stop here — the backfill happens on the next routine ERP upload; the cost table fills then.

- [ ] **Step 3: Verify the cost table**

Run:

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/torb.db')
n, dmin, dmax = conn.execute('SELECT COUNT(*), MIN(data_dl), MAX(data_dl) FROM vanzari_tobra').fetchone()
print(f'vanzari_tobra: {n} rows, {dmin} -> {dmax}')
"
```

Expected: row count > 0 with a plausible date range (if Step 2 ran).

- [ ] **Step 4: End-to-end check of the Auchan import (only if the Tobra file exists)**

If `docs_input/rapoarte/` contains a `*auchan*.xls` file:

Run: `python etl/import_vanzari_tobra_auchan.py`
Expected output includes the new line `-> Cost real Torb: X medie 30z | Y ultimul cost | Z valoare fisier` (new rows are all duplicates on a re-run, so `Inserate: 0` is normal — the point is the cost line printing without error).

- [ ] **Step 5: Full suite + lint**

Run: `python -m pytest tests/ -q` — expected: all pass (139 pre-existing + ~15 new).
Run: `ruff check .` — expected: no errors.

- [ ] **Step 6: Wrap up**

No commit here unless files changed. Hand back for branch integration (merge/PR) via the superpowers:finishing-a-development-branch skill.

---

## Out of scope (agreed)

- No retroactive recompute of the ~6,861 existing TOBRA rows in `tranzactii` — they pick up the rule on the next full DB rebuild (`rebuild_db.py` already runs the ERP import before the Auchan import, so ordering is correct).
- No sweep of other hard-coded values (agent name map, SKU-prefix rules, etc.) — migrate opportunistically when touched.
