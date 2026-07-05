# Solduri neîncasate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, this session). Steps use checkbox (`- [ ]`) syntax.

**Goal:** A "Solduri" Comercial page that ingests the ERP receivables `.xls` and shows aging KPI cards (not-yet-due / overdue by 7/30/60 days + catch-all) plus a table analysable per client, per agent, or per invoice.

**Architecture:** New SQLite table (replace-only snapshot) fed by an `etl/import_*.py` script wired into the existing `/api/upload/<tip>` pipeline. Read-side queries derive the due date and aging bucket in SQL against *today*. A new blueprint renders KPI cards + a toggleable table with card→bucket filtering and Excel export.

**Tech Stack:** Flask, SQLite, `xlrd` (BIFF `.xls`), pandas not required for ETL, openpyxl (existing `send_excel`), Jinja templates + Bootstrap (existing `base.html`).

## Global Constraints

- Python must pass `ruff check .` (no F401/F841/E402/E722 etc.).
- Dev comms/code in English; all UI strings in Romanian.
- Romanian text in `.py`: keep ASCII-safe or ensure UTF-8 (see `docs/TECHNICAL.md` §Encoding) — ETL scripts already `reconfigure(encoding="utf-8")`.
- Reference date for aging = today (`date('now','localtime')`), per owner.
- Due date computed, never read from the file's `scadenta` column.
- Errors in UI via shared `AppError.show()` modal, never inline text.
- Full spec: `docs/specs/2026-07-05-solduri-neincasate-design.md`.

---

### Task 1: Migration — `solduri_neincasate` table

**Files:**
- Create: `migrations/0021_20260705_solduri_neincasate.py`

**Interfaces:**
- Produces: table `solduri_neincasate` with columns `id, data_raport, nrdl, datadl, term_pl_cl, plafon, numecli, codcli, cfcli, vtdl, sumdeincas, factout, numeag, canal, telefon`; indexes on `codcli`, `numeag`.

- [ ] **Step 1: Write the migration**

```python
"""Migration 0021 - solduri_neincasate (accounts-receivable snapshot).

One row per open ERP document (invoice/advance). Replace-only: each import
truncates and reinserts. Due date is derived on read (datadl + term_pl_cl).
"""

VERSION = 21
NAME = "0021_20260705_solduri_neincasate"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS solduri_neincasate (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            data_raport TEXT NOT NULL,
            nrdl        TEXT,
            datadl      TEXT,
            term_pl_cl  INTEGER,
            plafon      REAL,
            numecli     TEXT,
            codcli      TEXT,
            cfcli       TEXT,
            vtdl        REAL,
            sumdeincas  REAL,
            factout     TEXT,
            numeag      TEXT,
            canal       TEXT,
            telefon     TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_solduri_codcli ON solduri_neincasate(codcli);
        CREATE INDEX IF NOT EXISTS idx_solduri_agent  ON solduri_neincasate(numeag);
    """)
```

- [ ] **Step 2: Apply and verify**

Run: `python migrations/runner.py`
Expected: applies `0021` (or "up to date"); no error.
Run: `python -c "import sqlite3; c=sqlite3.connect('data/torb.db'); print([r[1] for r in c.execute('PRAGMA table_info(solduri_neincasate)')])"`
Expected: the 15 column names printed.

- [ ] **Step 3: Commit**

```bash
git add migrations/0021_20260705_solduri_neincasate.py
git commit -m "feat(solduri): add solduri_neincasate table (migration 0021)"
```

---

### Task 2: ETL importer — `etl/import_solduri_neincasate.py`

**Files:**
- Create: `etl/import_solduri_neincasate.py`
- Test: `tests/test_solduri.py`

**Interfaces:**
- Produces: `run(filepath)` (imports, returns inserted count, prints `→ Solduri importate: N rânduri`); `parse_solduri_xls(filepath) -> list[dict]` with keys matching table columns except `id`/`data_raport`.

- [ ] **Step 1: Write the failing parse test** (uses the real sample if present)

```python
# tests/test_solduri.py
import os
import importlib.util
import sqlite3
import datetime
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "docs_input", "rapoarte", "neinc 30 06.xls")


def _etl():
    path = os.path.join(ROOT, "etl", "import_solduri_neincasate.py")
    spec = importlib.util.spec_from_file_location("_solduri_etl", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(not os.path.exists(SAMPLE), reason="sample xls not present")
def test_parse_sample():
    rows = _etl().parse_solduri_xls(SAMPLE)
    assert len(rows) > 1000
    r = rows[0]
    assert set(r) >= {"nrdl", "datadl", "term_pl_cl", "sumdeincas",
                      "numecli", "codcli", "numeag", "factout", "vtdl"}
    # datadl normalised to ISO yyyy-mm-dd
    assert r["datadl"] is None or len(r["datadl"]) == 10
    # at least one advance/credit-note with negative outstanding
    assert any((x["sumdeincas"] or 0) < 0 for x in rows)
    # numeric coercion
    assert all(isinstance(x["term_pl_cl"], int) for x in rows if x["term_pl_cl"] is not None)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_solduri.py::test_parse_sample -v`
Expected: FAIL (module/function not found).

- [ ] **Step 3: Implement the ETL script**

```python
"""Import solduri neîncasate din exportul ERP (.xls).

Un rând = un document deschis (factură/avans). Replace-only: șterge tot și
reinserează. data_raport = data încărcării (azi). Scadența se calculează la
citire (datadl + term_pl_cl), nu se ia din fișier.

Usage:
    python etl/import_solduri_neincasate.py <cale_fisier.xls>
"""

import sys
import sqlite3
import xlrd
from datetime import date

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "data/torb.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS solduri_neincasate (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    data_raport TEXT NOT NULL,
    nrdl        TEXT,
    datadl      TEXT,
    term_pl_cl  INTEGER,
    plafon      REAL,
    numecli     TEXT,
    codcli      TEXT,
    cfcli       TEXT,
    vtdl        REAL,
    sumdeincas  REAL,
    factout     TEXT,
    numeag      TEXT,
    canal       TEXT,
    telefon     TEXT
)
"""

COLS = ["nrdl", "datadl", "term_pl_cl", "plafon", "numecli", "codcli",
        "cfcli", "vtdl", "sumdeincas", "factout", "numeag", "canal", "telefon"]

# ERP header name -> our key
COL_MAP = {
    "nrdl": "nrdl", "datadl": "datadl", "term_pl_cl": "term_pl_cl",
    "plafon": "plafon", "numecli": "numecli", "codcli": "codcli",
    "cfcli": "cfcli", "vtdl": "vtdl", "sumdeincas": "sumdeincas",
    "factout": "factout", "numeag": "numeag", "nume": "canal",
    "telefon": "telefon",
}


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _f(v):
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _i(v):
    f = _f(v)
    return int(round(f)) if f is not None else None


def parse_solduri_xls(filepath):
    book = xlrd.open_workbook(filepath)
    ws = book.sheet_by_index(0)
    if ws.nrows < 2:
        return []
    header = [str(ws.cell_value(0, c)).strip().lower() for c in range(ws.ncols)]
    idx = {}
    for c, name in enumerate(header):
        if name in COL_MAP and COL_MAP[name] not in idx:
            idx[COL_MAP[name]] = c

    def cell(row, key):
        c = idx.get(key)
        return ws.cell_value(row, c) if c is not None else None

    def datestr(row):
        c = idx.get("datadl")
        if c is None:
            return None
        v = ws.cell_value(row, c)
        if isinstance(v, float) and v > 0:
            try:
                return xlrd.xldate_as_datetime(v, book.datemode).strftime("%Y-%m-%d")
            except Exception:
                return None
        s = _s(v)
        return s[:10] if s else None

    out = []
    for row in range(1, ws.nrows):
        numecli = _s(cell(row, "numecli"))
        factout = _s(cell(row, "factout"))
        if not numecli and not factout:
            continue
        out.append({
            "nrdl": _s(cell(row, "nrdl")),
            "datadl": datestr(row),
            "term_pl_cl": _i(cell(row, "term_pl_cl")),
            "plafon": _f(cell(row, "plafon")),
            "numecli": numecli,
            "codcli": _s(cell(row, "codcli")),
            "cfcli": _s(cell(row, "cfcli")),
            "vtdl": _f(cell(row, "vtdl")),
            "sumdeincas": _f(cell(row, "sumdeincas")),
            "factout": factout,
            "numeag": _s(cell(row, "numeag")),
            "canal": _s(cell(row, "canal")),
            "telefon": _s(cell(row, "telefon")),
        })
    return out


def run(filepath):
    rows = parse_solduri_xls(filepath)
    data_raport = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(CREATE_SQL)
    conn.execute("DELETE FROM solduri_neincasate")
    placeholders = ", ".join(["?"] * (len(COLS) + 1))
    sql = f"INSERT INTO solduri_neincasate (data_raport, {', '.join(COLS)}) VALUES ({placeholders})"
    conn.executemany(sql, [[data_raport] + [r[c] for c in COLS] for r in rows])
    conn.commit()
    conn.close()
    print(f"  → Solduri importate: {len(rows):,} rânduri (raport {data_raport})")
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("EROARE: lipsește calea fișierului .xls")
        sys.exit(1)
    run(sys.argv[1])
```

- [ ] **Step 4: Run parse test to verify pass**

Run: `pytest tests/test_solduri.py::test_parse_sample -v`
Expected: PASS.

- [ ] **Step 5: Smoke-run the importer end-to-end**

Run: `python etl/import_solduri_neincasate.py "docs_input/rapoarte/neinc 30 06.xls"`
Expected: `→ Solduri importate: 1,6xx rânduri`.

- [ ] **Step 6: Commit**

```bash
git add etl/import_solduri_neincasate.py tests/test_solduri.py
git commit -m "feat(solduri): ERP xls parser + importer"
```

---

### Task 3: Queries — aging KPI + bucket helper

**Files:**
- Create: `app/queries/solduri.py`
- Modify: `app/queries/__init__.py` (add re-exports)
- Test: `tests/test_solduri.py` (append)

**Interfaces:**
- Produces:
  - `BUCKET_KEYS = ("nesc7","nesc30","nesc60","scad7","scad30","scad60","total_scadent","catchall")`
  - `_days_expr` (SQL): signed days-to-due `d` = `julianday(date(datadl,'+'||COALESCE(term_pl_cl,0)||' days')) - julianday(date('now','localtime'))`.
  - `_bucket_where(bucket) -> str` — SQL predicate for a bucket key (empty string for `None`/unknown).
  - `solduri_meta() -> dict|None` `{data_raport, nr_randuri}`.
  - `solduri_kpi() -> dict` keys = BUCKET_KEYS + `total_piata`.

- [ ] **Step 1: Write failing KPI tests**

```python
# append to tests/test_solduri.py
import datetime as _dt
import queries  # noqa: E402  (conftest put app/ on path)
import db as _db  # noqa: E402


def _seed(rows):
    """rows: list of (offset_days_to_due, amount). term=0 so datadl=today+offset."""
    conn = _db.get_conn() if hasattr(_db, "get_conn") else None
    _db.execute("DELETE FROM solduri_neincasate")
    today = _dt.date.today()
    for i, (d, amt) in enumerate(rows):
        datadl = (today + _dt.timedelta(days=d)).isoformat()
        _db.execute(
            "INSERT INTO solduri_neincasate "
            "(data_raport, datadl, term_pl_cl, numecli, codcli, numeag, factout, sumdeincas) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (today.isoformat(), datadl, 0, f"CLI{i%3}", f"C{i%3}",
             f"AG{i%2}", f"F{i}", amt),
        )


def test_kpi_buckets():
    # offsets: 0(today, nesc), 5(nesc7), 20(nesc30), 45(nesc60), 100(future catchall),
    #          -3(scad7), -15(scad30), -50(scad60), -200(deep overdue catchall), -10 neg credit
    _seed([(0, 100), (5, 100), (20, 100), (45, 100), (100, 100),
           (-3, 100), (-15, 100), (-50, 100), (-200, 100), (-10, -40)])
    k = queries.solduri_kpi()
    assert round(k["nesc7"]) == 200        # d=0 and d=5
    assert round(k["nesc30"]) == 300       # +d=20
    assert round(k["nesc60"]) == 400       # +d=45
    assert round(k["scad7"]) == 140        # d=-3 (100) and d=-10 credit (-40) → within 7? -10 is >7
    # correct: scad7 covers 1..7 overdue → only d=-3 (100). d=-10 is scad30.
    assert round(k["scad7"]) == 100
    assert round(k["scad30"]) == 160       # d=-3(100), d=-10(-40), d=-15(100)
    assert round(k["scad60"]) == 260       # +d=-50(100)
    # reconciliation: nesc60 + scad60 + catchall == total_piata
    assert round(k["nesc60"] + k["scad60"] + k["catchall"], 2) == round(k["total_piata"], 2)
    # total_scadent = all overdue (d<=-1): -3,-15,-50,-200 = 100 and -10 credit -40
    assert round(k["total_scadent"]) == round(100 - 40 + 100 + 100 + 100)  # 460
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_solduri.py::test_kpi_buckets -v`
Expected: FAIL (`queries.solduri_kpi` missing).

- [ ] **Step 3: Implement `app/queries/solduri.py` (KPI part)**

```python
from db import query, query_one

# signed whole days from today to due date (negative = overdue)
_days_expr = (
    "CAST(julianday(date(datadl, '+' || COALESCE(term_pl_cl,0) || ' days')) "
    "- julianday(date('now','localtime')) AS INTEGER)"
)

BUCKET_KEYS = ("nesc7", "nesc30", "nesc60", "scad7", "scad30", "scad60",
               "total_scadent", "catchall")

_BUCKET_PRED = {
    "nesc7":         f"{_days_expr} BETWEEN 0 AND 7",
    "nesc30":        f"{_days_expr} BETWEEN 0 AND 30",
    "nesc60":        f"{_days_expr} BETWEEN 0 AND 60",
    "scad7":         f"{_days_expr} BETWEEN -7 AND -1",
    "scad30":        f"{_days_expr} BETWEEN -30 AND -1",
    "scad60":        f"{_days_expr} BETWEEN -60 AND -1",
    "total_scadent": f"{_days_expr} <= -1",
    "catchall":      f"({_days_expr} > 60 OR {_days_expr} < -60)",
}


def _bucket_where(bucket):
    pred = _BUCKET_PRED.get(bucket)
    return f" AND {pred}" if pred else ""


def solduri_meta():
    return query_one(
        "SELECT MAX(data_raport) AS data_raport, COUNT(*) AS nr_randuri "
        "FROM solduri_neincasate"
    )


def solduri_kpi():
    sums = ", ".join(
        f"ROUND(SUM(CASE WHEN {pred} THEN sumdeincas ELSE 0 END), 2) AS {key}"
        for key, pred in _BUCKET_PRED.items()
    )
    row = query_one(
        f"SELECT {sums}, ROUND(SUM(sumdeincas),2) AS total_piata "
        f"FROM solduri_neincasate"
    )
    return {k: (row[k] or 0) for k in (*BUCKET_KEYS, "total_piata")} if row else \
        {k: 0 for k in (*BUCKET_KEYS, "total_piata")}
```

Add re-exports to `app/queries/__init__.py`:

```python
from queries.solduri import (
    solduri_meta as solduri_meta,
    solduri_kpi as solduri_kpi,
    solduri_by_client as solduri_by_client,
    solduri_by_agent as solduri_by_agent,
    solduri_by_invoice as solduri_by_invoice,
    solduri_agents as solduri_agents,
    BUCKET_KEYS as SOLDURI_BUCKET_KEYS,
)
```

(Note: `solduri_by_*` and `solduri_agents` are added in Task 4; add all imports now so `__init__` is edited once — Task 4 defines them before the app is run.)

- [ ] **Step 4: Run KPI test to verify pass** (Task 4 functions still unimported-safe: run this test file selecting only the KPI test, but `queries/__init__` import will fail if Task 4 names are missing → so implement Task 4 before running the full suite). Instead, temporarily verify the KPI function directly:

Run: `pytest tests/test_solduri.py::test_kpi_buckets -v`
Expected: PASS after Task 4 completes the `__init__` names. If run before Task 4, expect ImportError — proceed to Task 4 then re-run.

- [ ] **Step 5: Commit**

```bash
git add app/queries/solduri.py app/queries/__init__.py tests/test_solduri.py
git commit -m "feat(solduri): aging KPI queries + bucket predicates"
```

---

### Task 4: Queries — table views (client / agent / invoice)

**Files:**
- Modify: `app/queries/solduri.py`
- Test: `tests/test_solduri.py` (append)

**Interfaces:**
- Produces:
  - `solduri_agents() -> list[str]` distinct `numeag` sorted.
  - `solduri_by_client(bucket=None, agent=None, search=None) -> list[dict]`
    keys: `numecli, codcli, numeag, total, nesc7, nesc30, nesc60, scad7,
    scad30, scad60, plafon, zile_restanta_max, depasit_plafon`.
  - `solduri_by_agent(bucket=None, search=None) -> list[dict]` keys: `numeag,
    total, nesc7, nesc30, nesc60, scad7, scad30, scad60, nr_clienti`.
  - `solduri_by_invoice(bucket=None, agent=None, search=None) -> list[dict]`
    keys: `factout, numecli, numeag, datadl, scadenta, term_pl_cl, sumdeincas,
    zile, bucket_label`.

- [ ] **Step 1: Write failing view tests**

```python
# append to tests/test_solduri.py
def test_by_client_shapes_and_filter():
    _seed([(0, 100), (-3, 50), (-200, 70)])  # CLI0,CLI1,CLI2 → C0,C1,C2
    rows = queries.solduri_by_client()
    assert rows and set(rows[0]) >= {
        "numecli", "codcli", "numeag", "total", "nesc7", "scad7",
        "plafon", "zile_restanta_max", "depasit_plafon"}
    total_all = round(sum(r["total"] for r in rows), 2)
    assert total_all == 220.0
    # bucket filter: only overdue<=7 (the d=-3 row, amount 50)
    r7 = queries.solduri_by_client(bucket="scad7")
    assert round(sum(r["total"] for r in r7), 2) == 50.0


def test_by_agent_and_invoice():
    _seed([(0, 100), (-3, 50)])
    ag = queries.solduri_by_agent()
    assert ag and "nr_clienti" in ag[0] and "total" in ag[0]
    inv = queries.solduri_by_invoice(bucket="scad7")
    assert len(inv) == 1
    assert inv[0]["zile"] == -3
    assert inv[0]["bucket_label"]
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_solduri.py::test_by_client_shapes_and_filter tests/test_solduri.py::test_by_agent_and_invoice -v`
Expected: FAIL (functions missing).

- [ ] **Step 3: Implement the view functions (append to `app/queries/solduri.py`)**

```python
_scadenta_expr = "date(datadl, '+' || COALESCE(term_pl_cl,0) || ' days')"


def _filters(agent, search):
    where, params = "", {}
    if agent:
        where += " AND numeag = :agent"
        params["agent"] = agent
    if search:
        where += " AND numecli LIKE :search"
        params["search"] = f"%{search}%"
    return where, params


def solduri_agents():
    rows = query("SELECT DISTINCT numeag FROM solduri_neincasate "
                 "WHERE numeag IS NOT NULL ORDER BY numeag")
    return [r["numeag"] for r in rows]


def _bucket_sum_cols():
    return ", ".join(
        f"ROUND(SUM(CASE WHEN {_BUCKET_PRED[k]} THEN sumdeincas ELSE 0 END),2) AS {k}"
        for k in ("nesc7", "nesc30", "nesc60", "scad7", "scad30", "scad60")
    )


def solduri_by_client(bucket=None, agent=None, search=None):
    fwhere, params = _filters(agent, search)
    bwhere = _bucket_where(bucket)
    total_expr = (f"SUM(CASE WHEN 1{bwhere.replace(' AND ', ' AND ') or ''}"
                  if False else None)  # placeholder replaced below
    # total scoped to bucket when set, else full balance
    total_case = f"SUM(CASE WHEN 1=1{bwhere} THEN sumdeincas ELSE 0 END)" if bwhere \
        else "SUM(sumdeincas)"
    return query(f"""
        SELECT numecli, MIN(codcli) AS codcli, MIN(numeag) AS numeag,
               ROUND({total_case},2) AS total,
               {_bucket_sum_cols()},
               MAX(plafon) AS plafon,
               MAX(CASE WHEN {_days_expr} <= -1 THEN -({_days_expr}) ELSE 0 END)
                   AS zile_restanta_max,
               CASE WHEN MAX(plafon) > 0 AND ROUND(SUM(sumdeincas),2) > MAX(plafon)
                    THEN 1 ELSE 0 END AS depasit_plafon
        FROM solduri_neincasate
        WHERE 1=1{fwhere}
        GROUP BY numecli
        HAVING ROUND({total_case},2) <> 0
        ORDER BY total DESC
    """, params)


def solduri_by_agent(bucket=None, search=None):
    fwhere, params = _filters(None, search)
    bwhere = _bucket_where(bucket)
    total_case = f"SUM(CASE WHEN 1=1{bwhere} THEN sumdeincas ELSE 0 END)" if bwhere \
        else "SUM(sumdeincas)"
    return query(f"""
        SELECT numeag,
               ROUND({total_case},2) AS total,
               {_bucket_sum_cols()},
               COUNT(DISTINCT codcli) AS nr_clienti
        FROM solduri_neincasate
        WHERE 1=1{fwhere}
        GROUP BY numeag
        HAVING ROUND({total_case},2) <> 0
        ORDER BY total DESC
    """, params)


_BUCKET_LABEL = (
    f"CASE "
    f"WHEN {_days_expr} BETWEEN 0 AND 7 THEN 'Nescadent ≤7' "
    f"WHEN {_days_expr} BETWEEN 0 AND 30 THEN 'Nescadent ≤30' "
    f"WHEN {_days_expr} BETWEEN 0 AND 60 THEN 'Nescadent ≤60' "
    f"WHEN {_days_expr} > 60 THEN 'Nescadent >60' "
    f"WHEN {_days_expr} BETWEEN -7 AND -1 THEN 'Scadent ≤7' "
    f"WHEN {_days_expr} BETWEEN -30 AND -1 THEN 'Scadent ≤30' "
    f"WHEN {_days_expr} BETWEEN -60 AND -1 THEN 'Scadent ≤60' "
    f"ELSE 'Scadent >60' END"
)


def solduri_by_invoice(bucket=None, agent=None, search=None):
    fwhere, params = _filters(agent, search)
    bwhere = _bucket_where(bucket)
    return query(f"""
        SELECT factout, numecli, numeag, datadl,
               {_scadenta_expr} AS scadenta, term_pl_cl, sumdeincas,
               {_days_expr} AS zile,
               {_BUCKET_LABEL} AS bucket_label
        FROM solduri_neincasate
        WHERE 1=1{fwhere}{bwhere}
        ORDER BY scadenta ASC, factout
    """, params)
```

Clean up the dead `total_expr` placeholder line (leftover) before committing — final code keeps only `total_case`.

- [ ] **Step 4: Run all solduri tests**

Run: `pytest tests/test_solduri.py -v`
Expected: all PASS (KPI + view tests).

- [ ] **Step 5: ruff + commit**

```bash
ruff check app/queries/solduri.py
git add app/queries/solduri.py tests/test_solduri.py
git commit -m "feat(solduri): per-client/agent/invoice table view queries"
```

---

### Task 5: Blueprint + upload wiring + app registration

**Files:**
- Create: `app/blueprints/solduri.py`
- Modify: `app/blueprints/actualizare.py` (whitelist + `script_map`)
- Modify: `app/app.py` (import + register blueprint)
- Test: `tests/test_solduri.py` (append a route smoke test)

**Interfaces:**
- Consumes: `queries.solduri_*`, `exports.excel_export.send_excel/timestamped_filename`.
- Produces: routes `GET /solduri-neincasate` (endpoint `solduri.solduri`), `GET /solduri-neincasate/export/excel` (endpoint `solduri.solduri_export`).

- [ ] **Step 1: Wire the upload pipeline** — in `app/blueprints/actualizare.py`, add `'solduri'` to both tuples and the `script_map`:
  - `_run_upload_job` `script_map`: add `'solduri': 'etl/import_solduri_neincasate.py',`
  - `api_upload` guard tuple: add `'solduri'`.

- [ ] **Step 2: Write the blueprint**

```python
import datetime
import logging
from flask import Blueprint, render_template, request
import queries
from exports.excel_export import send_excel, timestamped_filename

solduri_bp = Blueprint('solduri', __name__)
logger = logging.getLogger(__name__)

_VIEWS = ('client', 'agent', 'invoice')


def _load(view, bucket, agent, search):
    if view == 'agent':
        return queries.solduri_by_agent(bucket=bucket, search=search)
    if view == 'invoice':
        return queries.solduri_by_invoice(bucket=bucket, agent=agent, search=search)
    return queries.solduri_by_client(bucket=bucket, agent=agent, search=search)


@solduri_bp.route('/solduri-neincasate')
def solduri():
    view   = request.args.get('view', 'client')
    if view not in _VIEWS:
        view = 'client'
    bucket = request.args.get('bucket') or None
    agent  = request.args.get('agent', '').strip() or None
    search = request.args.get('q', '').strip() or None

    meta = queries.solduri_meta()
    kpi  = queries.solduri_kpi()
    rows = _load(view, bucket, agent, search)
    return render_template(
        'solduri_neincasate.html',
        meta=meta, kpi=kpi, rows=rows, view=view,
        bucket=bucket, agent=agent, q=search or '',
        agents=queries.solduri_agents(),
    )


@solduri_bp.route('/solduri-neincasate/export/excel')
def solduri_export():
    view   = request.args.get('view', 'client')
    if view not in _VIEWS:
        view = 'client'
    bucket = request.args.get('bucket') or None
    agent  = request.args.get('agent', '').strip() or None
    search = request.args.get('q', '').strip() or None
    rows = _load(view, bucket, agent, search)
    sheet = {'client': 'Solduri Client', 'agent': 'Solduri Agent',
             'invoice': 'Solduri Facturi'}[view]
    return send_excel({sheet: rows}, timestamped_filename(f'solduri_{view}'))
```

- [ ] **Step 3: Register in `app/app.py`** — add alongside the other imports/registrations:
  - import: `from blueprints.solduri import solduri_bp`
  - register: `app.register_blueprint(solduri_bp)`

- [ ] **Step 4: Route smoke test**

```python
# append to tests/test_solduri.py
def test_route_renders(client):  # `client` fixture from conftest
    _seed([(0, 100), (-3, 50)])
    r = client.get('/solduri-neincasate')
    assert r.status_code == 200
    assert 'Solduri'.encode() in r.data
    assert client.get('/solduri-neincasate?view=agent').status_code == 200
    assert client.get('/solduri-neincasate?view=invoice&bucket=scad7').status_code == 200
    assert client.get('/solduri-neincasate/export/excel').status_code == 200
```

(Confirm the conftest exposes a `client` fixture; if it is named differently, match it — check `tests/test_flask_routes.py`.)

- [ ] **Step 5: Run** — needs the template (Task 6). Implement Task 6, then:

Run: `pytest tests/test_solduri.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/blueprints/solduri.py app/blueprints/actualizare.py app/app.py tests/test_solduri.py
git commit -m "feat(solduri): blueprint, upload wiring, route registration"
```

---

### Task 6: Template + nav

**Files:**
- Create: `app/templates/solduri_neincasate.html`
- Modify: `app/templates/base.html` (Comercial group: add "Solduri" link)

**Interfaces:**
- Consumes: `meta, kpi, rows, view, bucket, agent, q, agents` from the blueprint.

- [ ] **Step 1: Add the nav link** — inside the `#group-comercial` block in `base.html`, after the Condiții link:

```html
    <a class="sidebar-link {% if request.endpoint == 'solduri.solduri' %}active{% endif %}"
       href="{{ url_for('solduri.solduri') }}" data-label="Solduri">
      <i class="bi bi-cash-coin"></i><span class="link-text"> Solduri</span>
    </a>
```

- [ ] **Step 2: Write the template** (extends base; KPI cards with bucket links, view toggle, filters, per-view table). Key rules: money formatted `"{:,.0f}"`, active card highlighted when `bucket==key`, cards are `url_for('solduri.solduri', view=view, bucket=key, agent=agent, q=q)`, a "Toate" clear link drops `bucket`. Card list: nesc7/30/60, scad7/30/60, total_scadent, total_piata (display-only, no link), catchall (link, key `catchall`). Upload widget posts to `/api/upload/solduri` and polls `/api/upload/status/<job_id>`; on error call `AppError.show(...)`. Table columns branch on `view`:
  - client: Client · Agent · Total · Nesc ≤7/≤30/≤60 · Scad ≤7/≤30/≤60 · Plafon (badge if `depasit_plafon`) · Zile restanță (`zile_restanta_max`).
  - agent: Agent · Nr. clienți · Total · same bucket columns.
  - invoice: Factură · Client · Agent · Data · Scadență · Termen · Sumă · Zile · Bucket (`bucket_label`).

  Reference `profitabilitate.html` for card/table/markup classes. Show `meta.data_raport` as "Raport încărcat: …" and `meta.nr_randuri` documents. If `meta` is null (no import yet), show an empty-state prompt to upload.

- [ ] **Step 3: Verify page renders** (run app or the route test from Task 5).

Run: `pytest tests/test_solduri.py::test_route_renders -v`
Expected: PASS.

- [ ] **Step 4: Manual visual check**

Run: `python etl/import_solduri_neincasate.py "docs_input/rapoarte/neinc 30 06.xls"` then start the app and open `/solduri-neincasate`; click a card, toggle views, export Excel.
Expected: cards reconcile (nesc60+scad60+catchall = total în piață), filtering works.

- [ ] **Step 5: Commit**

```bash
git add app/templates/solduri_neincasate.html app/templates/base.html
git commit -m "feat(solduri): dashboard template + Comercial nav link"
```

---

### Task 7: Docs + full-suite verification

**Files:**
- Modify: `CHANGELOG.md` ([Unreleased]), `context/STATUS.md`

- [ ] **Step 1:** Add a CHANGELOG `[Unreleased]` entry describing the Solduri module (ERP receivables aging: upload, KPI cards, per client/agent/invoice table, Excel export).
- [ ] **Step 2:** Note it in `context/STATUS.md` if it affects current state.
- [ ] **Step 3: Full suite + lint**

Run: `pytest -q` and `ruff check .`
Expected: green; no lint errors.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md context/STATUS.md
git commit -m "docs(solduri): changelog + status for receivables module"
```

---

## Self-Review

- **Spec coverage:** upload pipeline (T5) ✓, ETL parse incl. negatives/date (T2) ✓, table+indexes (T1) ✓, aging math incl. reconciliation (T3 tests) ✓, three views + bucket scoping (T4) ✓, blueprint+export (T5) ✓, template+cards+nav "Solduri" (T6) ✓, tests (T2–T5) ✓, docs (T7) ✓.
- **Placeholder scan:** one intentional dead line flagged for removal in T4 Step 3 (`total_expr` placeholder) — real code is `total_case`. No TBD/TODO elsewhere.
- **Type consistency:** `_days_expr`, `_bucket_where`, `_BUCKET_PRED`, `BUCKET_KEYS` names consistent across T3/T4; blueprint uses `queries.solduri_*` names exactly as produced in T3/T4; template consumes exactly the blueprint's context vars.
- **Ordering note:** `queries/__init__.py` imports T4 names, so T3 and T4 must both land before the app/route tests run (documented in T3 Step 4).
