# P&L Module Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relocate the standalone `pnl_app/` Flask app into TorbApp as a native, auth-gated module sharing `torb.db`, the migration runner, host deps, sidebar nav, and base template — no behavior changes.

**Architecture:** Per-type layout (blueprint / queries / exports / logic modules) following existing TorbApp precedent. Four `pnl_`-prefixed tables created by migration 0028. All DB access via host `db.query`/`db.get_db`. Excel read via host `xlrd`, export via host `openpyxl` inside the shared exports module. Nothing imported from `pnl_app/`; all logic rewritten.

**Tech Stack:** Flask (blueprints), SQLite (migration runner), xlrd≥2.0 (.xls read), openpyxl≥3.1 (export), pytest, ruff.

## Global Constraints

- **Zero new dependencies** — reuse host `xlrd>=2.0`, `openpyxl>=3.1`, `flask`. Do not add to `requirements.txt`. Nothing imported from `pnl_app/`.
- **Table prefix** — all four tables `pnl_`-prefixed: `pnl_balante_raw`, `pnl_mapping_conturi`, `pnl_config`, `pnl_import_log`.
- **Route prefix** — blueprint mounted under `/pnl`; all routes namespaced `/pnl/*`.
- **DB access** — reads via `db.query`/`db.query_one` (request-scoped); writes via `db.get_db()` (transient, caller commits/closes). No `init_db()` in module code — schema belongs to the migration.
- **Errors** — upload/scan failure paths surfaced via the shared `AppError.show()` modal (`app/static/js/app-error.js`), never inline text.
- **Encoding** — before editing any `.py` containing Romanian text, read `docs/TECHNICAL.md` §Encoding. UI strings Romanian; code/comments English.
- **Lint** — every task ends green: `ruff check .` zero errors, relevant `pytest` passing.
- **Migration idempotency** — 0028 uses `CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE` seeds; `pnl_balante_raw` keeps `UNIQUE(entitate, an, luna, cont) ON CONFLICT REPLACE`.

---

### Task 1: Migration 0028 — schema + reference seed

**Files:**
- Create: `migrations/0028_20260707_pnl_tables.py`
- Test: `tests/test_pnl_db.py`

**Interfaces:**
- Consumes: migration runner contract (`VERSION:int`, `NAME:str`, `up(conn)` — no commit).
- Produces: tables `pnl_balante_raw`, `pnl_mapping_conturi`, `pnl_config`, `pnl_import_log`; 32 seeded mapping rows; 9 seeded config rows.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pnl_db.py
import db


def test_pnl_tables_exist():
    names = {r['name'] for r in db.query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pnl_%'")}
    assert {'pnl_balante_raw', 'pnl_mapping_conturi',
            'pnl_config', 'pnl_import_log'} <= names


def test_pnl_seed_counts():
    m = db.query_one("SELECT COUNT(*) AS n FROM pnl_mapping_conturi")['n']
    c = db.query_one("SELECT COUNT(*) AS n FROM pnl_config")['n']
    assert m == 32
    assert c == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pnl_db.py -v`
Expected: FAIL — tables absent (migration not yet written).

- [ ] **Step 3: Write the migration**

```python
# migrations/0028_20260707_pnl_tables.py
"""Migration 0028 - P&L module tables (relocated from standalone pnl_app).

Four pnl_-prefixed tables. pnl_mapping_conturi (account -> P&L line) and
pnl_config (per-line alarm thresholds) are reference tables, seeded here.
pnl_balante_raw and pnl_import_log start empty on every environment; real
balance data arrives via the module's Excel upload.
"""

VERSION = 28
NAME = "0028_20260707_pnl_tables"

_MAPPING_SEED = [
    ('707',  'VENITURI DIN VANZARI MARFURI',                   'Venituri marfuri',                        1,  'venituri'),
    ('704',  'VENITURI DIN LUCR.EXEC.,SERV.PRESTATE',          'Venituri servicii',                       1,  'venituri'),
    ('709',  'REDUCERI COMERCIALE ACORDATE',                    'Reduceri comerciale acordate',           -1,  'venituri'),
    ('607',  'CHELT PRIVIND MARFURILE',                         'Cost marfa',                             -1,  'cogs'),
    ('609',  'REDUCERI COMERCIALE PRIMITE',                     'Reduceri comerciale primite',             1,  'cogs'),
    ('6022', 'CHELT COMBUSTIBIL',                               'Consumabile / utilitati / combustibil', -1,  'opex'),
    ('6028', 'CHELT. CU MATERIALE CONSUMABILE',                 'Consumabile / utilitati / combustibil', -1,  'opex'),
    ('603',  'CHELT PRIVIND MATERIALELE DE NATURA OB.INVENTAR', 'Consumabile / utilitati / combustibil', -1,  'opex'),
    ('605',  'CHELT. PRIVIND ENERGIA SI APA',                   'Consumabile / utilitati / combustibil', -1,  'opex'),
    ('611',  'CHELT. CU INTRETINEREA SI REPARATIILE',           'Servicii terti / logistica / marketing',-1,  'opex'),
    ('612',  'CHELT. CU REDEVENTELE LOC.GEST, CHIRII',          'Servicii terti / logistica / marketing',-1,  'opex'),
    ('613',  'CHELTUIELI CU PRIMELE DE ASIGURARE',              'Servicii terti / logistica / marketing',-1,  'opex'),
    ('622',  'CHELT. PRIVIND COMISIOANELE SI ONORARIILE',       'Servicii terti / logistica / marketing',-1,  'opex'),
    ('623',  'CHELT PROTOCOL, RECLAMA SI PUBLICITATE',          'Servicii terti / logistica / marketing',-1,  'opex'),
    ('624',  'CHELTUIELI CU TRANSPORTUL DE BUNURI SI PERSONAL', 'Servicii terti / logistica / marketing',-1,  'opex'),
    ('625',  'CHELT. CU DEPLASARI,DETASARI,TRANSFERURI',        'Servicii terti / logistica / marketing',-1,  'opex'),
    ('626',  'CHELT.POSTALE SI TAXE DE COMUNICATII',            'Servicii terti / logistica / marketing',-1,  'opex'),
    ('627',  'CHELT. CU SERVICII BANCARE SI ASIMILATE',         'Servicii terti / logistica / marketing',-1,  'opex'),
    ('628',  'ALTE CHELT. CU SERVICII EXECUT. DE TERTI',        'Servicii terti / logistica / marketing',-1,  'opex'),
    ('641',  'CHELT. SALARIILE  PERSONALULUI',                  'Cheltuieli personal',                   -1,  'opex'),
    ('6458', 'ALTE CHELTUIELI PRIVIND ASIGURARILE',             'Cheltuieli personal',                   -1,  'opex'),
    ('635',  'CHELT. CU ALTE IMPOZITE,TAXE,VARSAM.ASIM',        'Impozite si taxe',                      -1,  'opex'),
    ('6581', 'DEZPAGUBIRI, AMENZI SI PENALITATI',               'Alte cheltuieli exploatare',            -1,  'opex'),
    ('6584', 'CHELTUIELI CU SPONSORIZARI',                      'Alte cheltuieli exploatare',            -1,  'opex'),
    ('6588', 'ALTE CHELTUIELI DIN EXPLOATARE',                  'Alte cheltuieli exploatare',            -1,  'opex'),
    ('758',  'ALTE VENITURI DIN EXPLOATARE',                    'Alte venituri exploatare',               1,  'opex'),
    ('7588', 'ALTE VENITURI DIN EXPLOATARE',                    'Alte venituri exploatare',               1,  'opex'),
    ('6811', 'CHELT DE EXPLOATARE PRIVIND AMORTIZARILE',        'Amortizare',                            -1,  'amortizare'),
    ('765',  'VENITURI DIN DIFERENTE DE CURS VALUTAR',          'Venituri financiare',                    1,  'financiar'),
    ('766',  'VENITURI DIN DOBANZI',                            'Venituri financiare',                    1,  'financiar'),
    ('665',  'CHELT DIN DIFERENTE DE CURS VALUTAR',             'Cheltuieli financiare',                 -1,  'financiar'),
    ('666',  'CHELT.PRIVIND DOBANZILE',                         'Cheltuieli financiare',                 -1,  'financiar'),
    ('691',  'CHELT. CU IMPOZITUL PE PROFIT',                   'Impozit profit',                        -1,  'impozit'),
]

_CONFIG_SEED = [
    ('Cifra de afaceri neta',               -0.05, -0.10, None, None, 3, 'sus_bine'),
    ('Marja bruta',                         -0.05, -0.10, None, None, 3, 'sus_bine'),
    ('Marja bruta %',                       None,  None,  0.35, 0.30, 3, 'sus_bine'),
    ('EBITDA',                              -0.20, -0.40, None, None, 3, 'sus_bine'),
    ('EBITDA %',                            None,  None,  0.10, 0.05, 3, 'sus_bine'),
    ('Profit net',                          -0.20, -0.40, None, None, 3, 'sus_bine'),
    ('Cheltuieli personal',                  0.15,  0.30, None, None, 3, 'jos_bine'),
    ('Servicii terti / logistica / marketing', 0.15, 0.25, None, None, 3, 'jos_bine'),
    ('Reduceri comerciale acordate',         0.10,  0.20, None, None, 3, 'jos_bine'),
]


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pnl_balante_raw (
            id          INTEGER PRIMARY KEY,
            source_file TEXT,
            entitate    TEXT,
            an          INTEGER,
            luna        INTEGER,
            cont        TEXT,
            dencont     TEXT,
            sid  REAL, sic  REAL, sfd  REAL, sfc  REAL,
            rulld REAL, rullc REAL, rulcd REAL, rulcc REAL,
            UNIQUE(entitate, an, luna, cont) ON CONFLICT REPLACE
        );
        CREATE TABLE IF NOT EXISTS pnl_mapping_conturi (
            cont      TEXT PRIMARY KEY,
            dencont   TEXT,
            pnl_line  TEXT,
            semn      INTEGER,
            categorie TEXT
        );
        CREATE TABLE IF NOT EXISTS pnl_config (
            pnl_line          TEXT PRIMARY KEY,
            alarma_delta_warn REAL,
            alarma_delta_err  REAL,
            alarma_prag_warn  REAL,
            alarma_prag_err   REAL,
            alarma_trend_luni INTEGER DEFAULT 3,
            directie          TEXT DEFAULT 'sus_bine'
        );
        CREATE TABLE IF NOT EXISTS pnl_import_log (
            id          INTEGER PRIMARY KEY,
            timestamp   TEXT,
            source_file TEXT,
            entitate    TEXT,
            an          INTEGER,
            luna        INTEGER,
            rows        INTEGER,
            status      TEXT
        );
    """)
    conn.executemany(
        "INSERT OR IGNORE INTO pnl_mapping_conturi(cont,dencont,pnl_line,semn,categorie) VALUES(?,?,?,?,?)",
        _MAPPING_SEED,
    )
    conn.executemany(
        """INSERT OR IGNORE INTO pnl_config
           (pnl_line,alarma_delta_warn,alarma_delta_err,alarma_prag_warn,alarma_prag_err,alarma_trend_luni,directie)
           VALUES(?,?,?,?,?,?,?)""",
        _CONFIG_SEED,
    )
```

Note: seeds inlined (not a separate `migrations/seed/` module) because the runner loads migrations via `importlib` file-spec, where package-relative imports don't resolve. Self-contained is correct here.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pnl_db.py -v`
Expected: PASS (conftest rebuilds the temp DB through the runner, applying 0028).

- [ ] **Step 5: Lint + commit**

```bash
ruff check migrations/0028_20260707_pnl_tables.py tests/test_pnl_db.py
git add migrations/0028_20260707_pnl_tables.py tests/test_pnl_db.py
git commit -m "feat(pnl): migration 0028 - pnl_ tables + reference seed"
```

---

### Task 2: Query layer — `app/queries/pnl.py`

**Files:**
- Create: `app/queries/pnl.py`
- Modify: `app/queries/__init__.py` (add re-export block)
- Test: `tests/test_pnl_queries.py`

**Interfaces:**
- Consumes: `db.query` (`?`-placeholder tuple params → list of dicts); tables from Task 1.
- Produces: `pnl_available_years() -> list[int]`, `pnl_available_months(an:int, entitate:str) -> list[int]`, `pnl_mapping() -> dict[str,tuple[str,int]]`, `pnl_alarm_config() -> dict[str,dict]`, `pnl_rulcd(entitate:str, an:int, luna:int) -> dict[str,float]`, `pnl_config_rows() -> list[dict]`, `pnl_import_log(limit:int=50) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pnl_queries.py
import db
import queries


def _seed_rows():
    conn = db.get_db()
    conn.execute("DELETE FROM pnl_balante_raw")
    conn.executemany(
        """INSERT INTO pnl_balante_raw
           (source_file,entitate,an,luna,cont,dencont,sid,sic,sfd,sfc,rulld,rullc,rulcd,rulcc)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            ('f', 'torb', 2025, 1, '707', 'v', 0, 0, 0, 0, 0, 0, 1000.0, 0),
            ('f', 'torb', 2025, 2, '707', 'v', 0, 0, 0, 0, 0, 0, 2500.0, 0),
            ('f', 'tobra', 2025, 1, '707', 'v', 0, 0, 0, 0, 0, 0, 500.0, 0),
        ],
    )
    conn.commit()
    conn.close()


def test_available_years_and_months():
    _seed_rows()
    assert queries.pnl_available_years() == [2025]
    assert queries.pnl_available_months(2025, 'torb') == [1, 2]
    assert queries.pnl_available_months(2025, 'grup') == [1, 2]


def test_rulcd_and_mapping():
    _seed_rows()
    assert queries.pnl_rulcd('torb', 2025, 2) == {'707': 2500.0}
    mapping = queries.pnl_mapping()
    assert mapping['707'] == ('Venituri marfuri', 1)


def test_alarm_config_loaded():
    cfg = queries.pnl_alarm_config()
    assert cfg['EBITDA']['alarma_delta_err'] == -0.40
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pnl_queries.py -v`
Expected: FAIL — `module 'queries' has no attribute 'pnl_available_years'`.

- [ ] **Step 3: Write the query module**

```python
# app/queries/pnl.py
"""Read queries for the P&L module. All reads via host db.query."""
from db import query


def pnl_available_years():
    return [r['an'] for r in query(
        "SELECT DISTINCT an FROM pnl_balante_raw ORDER BY an")]


def pnl_available_months(an, entitate):
    if entitate == 'grup':
        rows = query(
            "SELECT DISTINCT luna FROM pnl_balante_raw WHERE an=? ORDER BY luna", (an,))
    else:
        rows = query(
            "SELECT DISTINCT luna FROM pnl_balante_raw WHERE entitate=? AND an=? ORDER BY luna",
            (entitate, an))
    return [r['luna'] for r in rows]


def pnl_mapping():
    return {r['cont']: (r['pnl_line'], int(r['semn']))
            for r in query("SELECT cont, pnl_line, semn FROM pnl_mapping_conturi")}


def pnl_alarm_config():
    return {r['pnl_line']: dict(r)
            for r in query("SELECT * FROM pnl_config")}


def pnl_rulcd(entitate, an, luna):
    return {r['cont']: r['rulcd'] for r in query(
        "SELECT cont, rulcd FROM pnl_balante_raw WHERE entitate=? AND an=? AND luna=?",
        (entitate, an, luna))}


def pnl_config_rows():
    return query("SELECT * FROM pnl_config ORDER BY pnl_line")


def pnl_import_log(limit=50):
    return query(
        "SELECT * FROM pnl_import_log ORDER BY timestamp DESC LIMIT ?", (limit,))
```

- [ ] **Step 4: Re-export from the queries package**

Add to the end of `app/queries/__init__.py`:

```python
from queries.pnl import (
    pnl_available_years as pnl_available_years,
    pnl_available_months as pnl_available_months,
    pnl_mapping as pnl_mapping,
    pnl_alarm_config as pnl_alarm_config,
    pnl_rulcd as pnl_rulcd,
    pnl_config_rows as pnl_config_rows,
    pnl_import_log as pnl_import_log,
)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_pnl_queries.py -v`
Expected: PASS.

- [ ] **Step 6: Lint + commit**

```bash
ruff check app/queries/pnl.py app/queries/__init__.py tests/test_pnl_queries.py
git add app/queries/pnl.py app/queries/__init__.py tests/test_pnl_queries.py
git commit -m "feat(pnl): read query layer"
```

---

### Task 3: Compute logic — `app/pnl_logic.py`

**Files:**
- Create: `app/pnl_logic.py`
- Test: `tests/test_pnl_logic.py`

**Interfaces:**
- Consumes: `queries.pnl_*` from Task 2.
- Produces: `PNL_STRUCTURE: list[tuple[str,str,str]]`; `compute_pnl_month(entitate, an, luna) -> dict`; `compute_pnl_year(entitate, an) -> dict[int,dict]`; `compute_ytd(entitate, an, through_luna) -> dict`; `compute_alarm(current, prior, pct_value, cfg) -> dict`; `compute_trend_alarm(entitate, pnl_line, an, luna, n_luni=3) -> bool`; `available_years() -> list[int]`; `load_alarm_config() -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pnl_logic.py
import db
import pnl_logic


def _seed(rows):
    conn = db.get_db()
    conn.execute("DELETE FROM pnl_balante_raw")
    conn.executemany(
        """INSERT INTO pnl_balante_raw
           (source_file,entitate,an,luna,cont,dencont,sid,sic,sfd,sfc,rulld,rullc,rulcd,rulcc)
           VALUES('f',?,?,?,?,'',0,0,0,0,0,0,?,0)""",
        rows)
    conn.commit()
    conn.close()


def test_month_subtotals():
    # Jan: sales 707=1000, cost 607=400 -> CA 1000, COGS -400, marja 600
    _seed([('torb', 2025, 1, '707', 1000.0), ('torb', 2025, 1, '607', 400.0)])
    m = pnl_logic.compute_pnl_month('torb', 2025, 1)
    assert m['CIFRA DE AFACERI NETA'] == 1000.0
    assert m['COGS NET'] == -400.0
    assert m['MARJA BRUTA'] == 600.0
    assert round(m['Marja bruta %'], 1) == 60.0


def test_month_uses_rulcd_delta():
    # cumulative rulcd: Jan 1000, Feb 2500 -> Feb monthly = 1500
    _seed([('torb', 2025, 1, '707', 1000.0), ('torb', 2025, 2, '707', 2500.0)])
    assert pnl_logic.compute_pnl_month('torb', 2025, 2)['CIFRA DE AFACERI NETA'] == 1500.0


def test_grup_sums_entities():
    _seed([('torb', 2025, 1, '707', 1000.0), ('tobra', 2025, 1, '707', 500.0)])
    assert pnl_logic.compute_pnl_month('grup', 2025, 1)['CIFRA DE AFACERI NETA'] == 1500.0


def test_alarm_cost_direction():
    cfg = {'alarma_delta_warn': 0.15, 'alarma_delta_err': 0.30, 'directie': 'jos_bine'}
    # cost up 50% vs prior -> error
    assert pnl_logic.compute_alarm(150, 100, None, cfg)['delta_severity'] == 'error'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pnl_logic.py -v`
Expected: FAIL — `No module named 'pnl_logic'`.

- [ ] **Step 3: Write the compute module**

```python
# app/pnl_logic.py
"""P&L computation (relocated from pnl_app). All data access via queries.pnl."""
import queries

# Ordered display structure: (row_type, label, key). row_type: line|subtotal|pct
PNL_STRUCTURE = [
    ('line',     'Venituri marfuri',                      'Venituri marfuri'),
    ('line',     'Venituri servicii',                     'Venituri servicii'),
    ('line',     'Reduceri comerciale acordate',          'Reduceri comerciale acordate'),
    ('subtotal', 'CIFRA DE AFACERI NETA',                 'CIFRA DE AFACERI NETA'),
    ('line',     'Cost marfa',                            'Cost marfa'),
    ('line',     'Reduceri comerciale primite',           'Reduceri comerciale primite'),
    ('subtotal', 'COGS NET',                              'COGS NET'),
    ('subtotal', 'MARJA BRUTA',                           'MARJA BRUTA'),
    ('pct',      'Marja bruta %',                         'Marja bruta %'),
    ('line',     'Consumabile / utilitati / combustibil', 'Consumabile / utilitati / combustibil'),
    ('line',     'Servicii terti / logistica / marketing','Servicii terti / logistica / marketing'),
    ('line',     'Cheltuieli personal',                   'Cheltuieli personal'),
    ('line',     'Impozite si taxe',                      'Impozite si taxe'),
    ('line',     'Alte cheltuieli exploatare',            'Alte cheltuieli exploatare'),
    ('line',     'Alte venituri exploatare',              'Alte venituri exploatare'),
    ('subtotal', 'EBITDA',                                'EBITDA'),
    ('pct',      'EBITDA %',                              'EBITDA %'),
    ('line',     'Amortizare',                            'Amortizare'),
    ('subtotal', 'EBIT',                                  'EBIT'),
    ('line',     'Venituri financiare',                   'Venituri financiare'),
    ('line',     'Cheltuieli financiare',                 'Cheltuieli financiare'),
    ('subtotal', 'PROFIT INAINTE DE IMPOZIT',             'PROFIT INAINTE DE IMPOZIT'),
    ('line',     'Impozit profit',                        'Impozit profit'),
    ('subtotal', 'PROFIT NET',                            'PROFIT NET'),
    ('pct',      'Profit net %',                          'Profit net %'),
]


def _raw_monthly(entitate, an, luna):
    """{cont: monthly_amount} = rulcd_current - rulcd_prior (raw delta)."""
    cur = queries.pnl_rulcd(entitate, an, luna)
    prior = queries.pnl_rulcd(entitate, an, luna - 1) if luna > 1 else {}
    return {cont: cur[cont] - prior.get(cont, 0.0) for cont in cur}


def compute_pnl_month(entitate, an, luna):
    """Full P&L dict for one entity+month. entitate='grup' sums torb+tobra."""
    mapping = queries.pnl_mapping()
    if entitate == 'grup':
        torb = _raw_monthly('torb', an, luna)
        tobra = _raw_monthly('tobra', an, luna)
        raw = {c: torb.get(c, 0) + tobra.get(c, 0) for c in set(torb) | set(tobra)}
    else:
        raw = _raw_monthly(entitate, an, luna)

    lines = {}
    for cont, amount in raw.items():
        if cont not in mapping:
            continue
        pnl_line, semn = mapping[cont]
        lines[pnl_line] = lines.get(pnl_line, 0.0) + semn * amount

    ca_neta = (lines.get('Venituri marfuri', 0)
               + lines.get('Venituri servicii', 0)
               + lines.get('Reduceri comerciale acordate', 0))
    cogs_net = (lines.get('Cost marfa', 0)
                + lines.get('Reduceri comerciale primite', 0))
    marja_bruta = ca_neta + cogs_net
    opex = (lines.get('Consumabile / utilitati / combustibil', 0)
            + lines.get('Servicii terti / logistica / marketing', 0)
            + lines.get('Cheltuieli personal', 0)
            + lines.get('Impozite si taxe', 0)
            + lines.get('Alte cheltuieli exploatare', 0)
            + lines.get('Alte venituri exploatare', 0))
    ebitda = marja_bruta + opex
    ebit = ebitda + lines.get('Amortizare', 0)
    fin = lines.get('Venituri financiare', 0) + lines.get('Cheltuieli financiare', 0)
    pbi = ebit + fin
    profit_net = pbi + lines.get('Impozit profit', 0)

    lines['CIFRA DE AFACERI NETA'] = ca_neta
    lines['COGS NET'] = cogs_net
    lines['MARJA BRUTA'] = marja_bruta
    lines['Marja bruta %'] = (marja_bruta / ca_neta * 100) if ca_neta else 0.0
    lines['EBITDA'] = ebitda
    lines['EBITDA %'] = (ebitda / ca_neta * 100) if ca_neta else 0.0
    lines['EBIT'] = ebit
    lines['PROFIT INAINTE DE IMPOZIT'] = pbi
    lines['PROFIT NET'] = profit_net
    lines['Profit net %'] = (profit_net / ca_neta * 100) if ca_neta else 0.0
    return lines


def compute_pnl_year(entitate, an):
    """{luna: pnl_dict} for all available months."""
    luni = queries.pnl_available_months(an, entitate)
    return {luna: compute_pnl_month(entitate, an, luna) for luna in luni}


def compute_ytd(entitate, an, through_luna):
    """Sum Jan..through_luna. % lines recomputed from sums."""
    months = compute_pnl_year(entitate, an)
    totals = {}
    pct_keys = {'Marja bruta %', 'EBITDA %', 'Profit net %'}
    for luna in range(1, through_luna + 1):
        for k, v in months.get(luna, {}).items():
            if k not in pct_keys:
                totals[k] = totals.get(k, 0.0) + v
    ca = totals.get('CIFRA DE AFACERI NETA', 0)
    totals['Marja bruta %'] = (totals.get('MARJA BRUTA', 0) / ca * 100) if ca else 0.0
    totals['EBITDA %'] = (totals.get('EBITDA', 0) / ca * 100) if ca else 0.0
    totals['Profit net %'] = (totals.get('PROFIT NET', 0) / ca * 100) if ca else 0.0
    return totals


def available_years():
    return queries.pnl_available_years()


def load_alarm_config():
    return queries.pnl_alarm_config()


def compute_alarm(current, prior, pct_value, cfg):
    """{'delta_severity': ..., 'prag_severity': ...} — severities ok|warning|error|success|None."""
    result = {'delta_severity': None, 'prag_severity': None}

    dw = cfg.get('alarma_delta_warn')
    de = cfg.get('alarma_delta_err')
    if dw is not None and prior and prior != 0 and current is not None:
        delta = (current - prior) / abs(prior)
        directie = cfg.get('directie', 'sus_bine')
        if directie == 'sus_bine':
            if de is not None and delta <= de:
                result['delta_severity'] = 'error'
            elif delta <= dw:
                result['delta_severity'] = 'warning'
            elif delta >= 0.05:
                result['delta_severity'] = 'success'
            else:
                result['delta_severity'] = 'ok'
        else:  # jos_bine (costs — increase is bad)
            if de is not None and delta >= de:
                result['delta_severity'] = 'error'
            elif delta >= dw:
                result['delta_severity'] = 'warning'
            elif delta <= -0.05:
                result['delta_severity'] = 'success'
            else:
                result['delta_severity'] = 'ok'

    pw = cfg.get('alarma_prag_warn')
    pe = cfg.get('alarma_prag_err')
    if pw is not None and pct_value is not None:
        pct = pct_value / 100 if pct_value > 1 else pct_value
        if pe is not None and pct <= pe:
            result['prag_severity'] = 'error'
        elif pct <= pw:
            result['prag_severity'] = 'warning'
        else:
            result['prag_severity'] = 'ok'

    return result


def compute_trend_alarm(entitate, pnl_line, an, luna, n_luni=3):
    """True if pnl_line deteriorated n_luni consecutive months."""
    if luna < n_luni:
        return False
    values = []
    for m in range(luna - n_luni + 1, luna + 1):
        values.append(compute_pnl_month(entitate, an, m).get(pnl_line, 0.0))
    return all(values[i] < values[i - 1] for i in range(1, len(values)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pnl_logic.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
ruff check app/pnl_logic.py tests/test_pnl_logic.py
git add app/pnl_logic.py tests/test_pnl_logic.py
git commit -m "feat(pnl): P&L compute logic"
```

---

### Task 4: Balante import — `app/pnl_import.py`

**Files:**
- Create: `app/pnl_import.py`
- Test: `tests/test_pnl_import.py`

**Interfaces:**
- Consumes: host `xlrd`; `db.get_db()`; `app.config` folders from Task 6 (import via `from config import settings` — used only in `scan_folders`).
- Produces: `detect_entity(filename) -> str`; `parse_period(filename) -> tuple[int,int]`; `read_xls_rows(path) -> list[dict]`; `persist_rows(source, entitate, an, luna, rows) -> int`; `import_file(path) -> dict`; `scan_folders() -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pnl_import.py
import pytest
import db
import pnl_import


def test_detect_entity():
    assert pnl_import.detect_entity('bal 05 2025 tobra.xls') == 'tobra'
    assert pnl_import.detect_entity('01 2025 torb.xls') == 'torb'
    assert pnl_import.detect_entity('01 2025.xls') == 'torb'  # default


def test_parse_period():
    assert pnl_import.parse_period('01 2025.xls') == (2025, 1)
    assert pnl_import.parse_period('bal 05 2025 tobra.xls') == (2025, 5)
    with pytest.raises(ValueError):
        pnl_import.parse_period('garbage.xls')


def test_persist_rows_and_log():
    conn = db.get_db()
    conn.execute("DELETE FROM pnl_balante_raw")
    conn.execute("DELETE FROM pnl_import_log")
    conn.commit()
    conn.close()
    rows = [{'cont': '707', 'dencont': 'v', 'rulcd': 1000.0}]
    n = pnl_import.persist_rows('src.xls', 'torb', 2025, 1, rows)
    assert n == 1
    got = db.query_one(
        "SELECT rulcd FROM pnl_balante_raw WHERE entitate='torb' AND an=2025 AND luna=1 AND cont='707'")
    assert got['rulcd'] == 1000.0
    log = db.query_one("SELECT status, rows FROM pnl_import_log ORDER BY id DESC LIMIT 1")
    assert log['status'] == 'ok' and log['rows'] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pnl_import.py -v`
Expected: FAIL — `No module named 'pnl_import'`.

- [ ] **Step 3: Write the import module**

```python
# app/pnl_import.py
"""Balance (.xls) import for the P&L module. Reads via host xlrd, writes via db.get_db."""
import re
import os
import io
import datetime
import xlrd
import db

_NUMERIC_COLS = ('sid', 'sic', 'sfd', 'sfc', 'rulld', 'rullc', 'rulcd', 'rulcc')


def detect_entity(filename):
    """'tobra' takes precedence; default 'torb'."""
    name = filename.lower()
    if 'tobra' in name:
        return 'tobra'
    if 'torb' in name:
        return 'torb'
    return 'torb'


def parse_period(filename):
    """(year, month) from filename, e.g. '01 2025.xls', 'bal 05 2025 tobra.xls'."""
    nums = re.findall(r'\d+', os.path.basename(filename))
    candidates = [(int(n), int(m)) for n, m in zip(nums, nums[1:]) if len(m) == 4]
    if candidates:
        month, year = candidates[0]
        if not (1 <= month <= 12):
            raise ValueError(f"Invalid month {month} in filename: {filename}")
        return year, month
    raise ValueError(f"Cannot parse period from filename: {filename}")


def read_xls_rows(path):
    """All rows from a .xls balance file as list of dicts (host xlrd pattern)."""
    wb = xlrd.open_workbook(path, logfile=io.StringIO())
    ws = wb.sheet_by_index(0)
    if ws.nrows < 2:
        return []
    header = [str(ws.cell_value(0, c)).strip().lower() for c in range(ws.ncols)]
    rows = []
    for i in range(1, ws.nrows):
        row = {col: ws.cell_value(i, j) for j, col in enumerate(header)}
        if row.get('cont'):
            row['cont'] = str(row['cont']).strip().split('.')[0]
            rows.append(row)
    return rows


def persist_rows(source, entitate, an, luna, rows):
    """Insert parsed rows into pnl_balante_raw + write an 'ok' import_log entry. Returns count."""
    conn = db.get_db()
    try:
        records = []
        for r in rows:
            cont = str(r.get('cont', '') or '')
            if not cont:
                continue
            records.append((
                source, entitate, an, luna, cont, str(r.get('dencont', '')),
                *(float(r.get(c, 0) or 0) for c in _NUMERIC_COLS),
            ))
        conn.executemany("""
            INSERT OR REPLACE INTO pnl_balante_raw
            (source_file,entitate,an,luna,cont,dencont,sid,sic,sfd,sfc,rulld,rullc,rulcd,rulcc)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, records)
        conn.execute("""
            INSERT INTO pnl_import_log(timestamp,source_file,entitate,an,luna,rows,status)
            VALUES(?,?,?,?,?,?,'ok')
        """, (datetime.datetime.now().isoformat(), source, entitate, an, luna, len(records)))
        conn.commit()
        return len(records)
    finally:
        conn.close()


def _log_error(source, entitate, an, luna, error):
    conn = db.get_db()
    try:
        conn.execute("""
            INSERT INTO pnl_import_log(timestamp,source_file,entitate,an,luna,rows,status)
            VALUES(?,?,?,?,?,0,?)
        """, (datetime.datetime.now().isoformat(), source, entitate, an, luna, f'error: {error}'))
        conn.commit()
    finally:
        conn.close()


def import_file(path):
    """Import one .xls. Returns {'ok': bool, 'rows': int, 'error': str|None}."""
    filename = os.path.basename(path)
    entitate = detect_entity(filename)
    try:
        an, luna = parse_period(filename)
    except ValueError as e:
        _log_error(path, entitate, 0, 0, str(e))
        return {'ok': False, 'rows': 0, 'error': str(e)}
    try:
        rows = read_xls_rows(path)
    except Exception as e:
        error_msg = f'xlrd error: {e}'
        _log_error(path, entitate, an, luna, error_msg)
        return {'ok': False, 'rows': 0, 'error': error_msg}
    n = persist_rows(path, entitate, an, luna, rows)
    return {'ok': True, 'rows': n, 'error': None}


def scan_folders():
    """Import .xls files in configured folders not already imported. Returns list of results."""
    from config import settings
    imported = {r['source_file'] for r in db.query(
        "SELECT source_file FROM pnl_import_log WHERE status='ok'")}
    results = []
    for folder in (settings.pnl_torb_folder, settings.pnl_tobra_folder):
        if not folder or not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.lower().endswith('.xls'):
                continue
            full = os.path.join(folder, fname)
            if full in imported:
                continue
            result = import_file(full)
            result['filename'] = fname
            results.append(result)
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pnl_import.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
ruff check app/pnl_import.py tests/test_pnl_import.py
git add app/pnl_import.py tests/test_pnl_import.py
git commit -m "feat(pnl): balante .xls import"
```

---

### Task 5: Excel export — extend `app/exports/excel_export.py`

**Files:**
- Modify: `app/exports/excel_export.py` (append P&L builders)
- Test: `tests/test_pnl_export.py`

**Interfaces:**
- Consumes: `pnl_logic` (Task 3); existing `timestamped_filename` in the module.
- Produces: `build_pnl_xlsx(an) -> io.BytesIO` (workbook: 3 P&L sheets + KPI summary).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pnl_export.py
import openpyxl
import db
from exports.excel_export import build_pnl_xlsx


def _seed():
    conn = db.get_db()
    conn.execute("DELETE FROM pnl_balante_raw")
    conn.executemany(
        """INSERT INTO pnl_balante_raw
           (source_file,entitate,an,luna,cont,dencont,sid,sic,sfd,sfc,rulld,rullc,rulcd,rulcc)
           VALUES('f',?,?,?,'707','',0,0,0,0,0,0,?,0)""",
        [('torb', 2025, 1, 1000.0), ('tobra', 2025, 1, 500.0)])
    conn.commit()
    conn.close()


def test_build_pnl_xlsx_sheets():
    _seed()
    buf = build_pnl_xlsx(2025)
    wb = openpyxl.load_workbook(buf)
    assert wb.sheetnames == ['P&L Torb', 'P&L Tobra', 'P&L Grup', 'KPI Summary']
    ws = wb['P&L Torb']
    assert ws['A1'].value == 'Linie P&L'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pnl_export.py -v`
Expected: FAIL — `cannot import name 'build_pnl_xlsx'`.

- [ ] **Step 3: Append the builders**

Add to `app/exports/excel_export.py` (after the existing exports; module already imports `openpyxl`, `Font`, `PatternFill`, `Alignment`, `get_column_letter`, `BytesIO as`... — add `import io` reference via existing `BytesIO`; reuse `Font`/`PatternFill`/`Alignment`/`get_column_letter` already imported at top):

```python
# ── P&L module export (relocated from pnl_app) ──────────────────────────────
_PNL_MONTHS_RO = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
                  'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
_PNL_RED = PatternFill('solid', fgColor='FFCCCC')
_PNL_YELLOW = PatternFill('solid', fgColor='FFF3CC')
_PNL_GREEN = PatternFill('solid', fgColor='CCFFCC')
_PNL_GREY = PatternFill('solid', fgColor='F0F0F0')
_PNL_HEADER = PatternFill('solid', fgColor='1F3864')


def _pnl_write_sheet(ws, entitate, an):
    import pnl_logic
    py = an - 1
    luni = pnl_logic.compute_pnl_year(entitate, an).keys()
    luni = sorted(luni)
    data_cy = pnl_logic.compute_pnl_year(entitate, an)
    data_py = pnl_logic.compute_pnl_year(entitate, py)
    max_luna = max(luni) if luni else 0
    ytd_cy = pnl_logic.compute_ytd(entitate, an, max_luna) if max_luna else {}
    ytd_py = pnl_logic.compute_ytd(entitate, py, max_luna) if luni else {}
    alarm_config = pnl_logic.load_alarm_config()

    headers = ['Linie P&L']
    for luna in luni:
        headers += [f'{_PNL_MONTHS_RO[luna - 1]} {an}', f'Delta% vs {py}']
    headers += [f'YTD {an}', 'Delta% YTD']
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = _PNL_HEADER
        cell.font = Font(bold=True, color='FFFFFF')
        cell.alignment = Alignment(horizontal='center')

    for row_type, label, key in pnl_logic.PNL_STRUCTURE:
        row_data = [label]
        for luna in luni:
            v = data_cy.get(luna, {}).get(key) or 0
            vp = data_py.get(luna, {}).get(key) or 0
            delta = round((v - vp) / abs(vp) * 100, 1) if vp else None
            row_data += [round(v, 2) if key.endswith('%') else round(v, 0), delta]
        ytd_v = ytd_cy.get(key) or 0
        ytd_vp = ytd_py.get(key) or 0
        ytd_delta = round((ytd_v - ytd_vp) / abs(ytd_vp) * 100, 1) if ytd_vp else None
        row_data += [round(ytd_v, 2) if key.endswith('%') else round(ytd_v, 0), ytd_delta]
        ws.append(row_data)

        excel_row = ws.max_row
        if row_type == 'subtotal':
            for cell in ws[excel_row]:
                cell.font = Font(bold=True)
                cell.fill = _PNL_GREY
        elif row_type == 'pct':
            for cell in ws[excel_row]:
                cell.font = Font(italic=True, color='555555')

        cfg = alarm_config.get(key, {})
        col_idx = 2
        for luna in luni:
            v = data_cy.get(luna, {}).get(key) or 0
            vp = data_py.get(luna, {}).get(key) or 0
            pct_val = v if key.endswith('%') else None
            alarm = pnl_logic.compute_alarm(v, vp, pct_val, cfg)
            sev = alarm.get('delta_severity') or alarm.get('prag_severity')
            fill = {'error': _PNL_RED, 'warning': _PNL_YELLOW, 'success': _PNL_GREEN}.get(sev)
            if fill:
                ws.cell(excel_row, col_idx).fill = fill
            col_idx += 2

    ws.column_dimensions['A'].width = 38
    for col in range(2, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(col)].width = 13
    ws.freeze_panes = 'B2'


def _pnl_write_kpi(ws, an):
    import pnl_logic
    py = an - 1
    kpi_keys = ['CIFRA DE AFACERI NETA', 'MARJA BRUTA', 'Marja bruta %',
                'EBITDA', 'EBITDA %', 'PROFIT NET', 'Profit net %']
    ws.append(['KPI'] + [f'YTD {an}', f'YTD {py}', 'Delta', 'Delta %'] * 3)
    ws[1][0].font = Font(bold=True)
    for entitate, label in [('torb', 'Torb'), ('tobra', 'Tobra'), ('grup', 'Grup')]:
        luni = sorted(pnl_logic.compute_pnl_year(entitate, an).keys())
        max_luna = max(luni) if luni else 0
        ytd_cy = pnl_logic.compute_ytd(entitate, an, max_luna) if max_luna else {}
        ytd_py = pnl_logic.compute_ytd(entitate, py, max_luna) if luni else {}
        ws.append([f'--- {label} ---'])
        ws[ws.max_row][0].font = Font(bold=True, italic=True)
        for key in kpi_keys:
            v = ytd_cy.get(key) or 0
            vp = ytd_py.get(key) or 0
            d = v - vp
            dp = round((d / abs(vp)) * 100, 1) if vp else None
            ws.append([key,
                       round(v, 2) if key.endswith('%') else round(v, 0),
                       round(vp, 2) if key.endswith('%') else round(vp, 0),
                       round(d, 0), dp])
    ws.column_dimensions['A'].width = 30
    for col in ['B', 'C', 'D', 'E']:
        ws.column_dimensions[col].width = 15


def build_pnl_xlsx(an):
    """Styled P&L workbook: 3 entity sheets + KPI summary. Returns BytesIO."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for entitate, sheet_name in [('torb', 'P&L Torb'), ('tobra', 'P&L Tobra'), ('grup', 'P&L Grup')]:
        _pnl_write_sheet(wb.create_sheet(sheet_name), entitate, an)
    _pnl_write_kpi(wb.create_sheet('KPI Summary'), an)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pnl_export.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
ruff check app/exports/excel_export.py tests/test_pnl_export.py
git add app/exports/excel_export.py tests/test_pnl_export.py
git commit -m "feat(pnl): styled Excel export in shared exports module"
```

---

### Task 6: Config + blueprint — `app/config.py`, `app/blueprints/pnl.py`, register

**Files:**
- Modify: `app/config.py` (add two folder settings)
- Create: `app/blueprints/pnl.py`
- Modify: `app/app.py` (import + register `pnl_bp`)
- Test: `tests/test_pnl_routes.py`

**Interfaces:**
- Consumes: `pnl_logic`, `pnl_import`, `queries.pnl_*`, `build_pnl_xlsx`, `timestamped_filename`; host auth gate.
- Produces: `pnl_bp` (Blueprint, `url_prefix='/pnl'`); `settings.pnl_torb_folder`, `settings.pnl_tobra_folder`.

- [ ] **Step 1: Add config settings**

In `app/config.py`, inside the `Settings` class (after `log_level`):

```python
    pnl_torb_folder: str = r"G:\My Drive\1_a_Torb\Buget2026\Balante 2025"
    pnl_tobra_folder: str = r"G:\My Drive\1_a_Torb\Buget2026\Balante 2025\balante"
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_pnl_routes.py
def test_pnl_page(client):
    rv = client.get('/pnl')
    assert rv.status_code == 200


def test_pnl_import_page(client):
    rv = client.get('/pnl/import')
    assert rv.status_code == 200


def test_pnl_alarm_config_page(client):
    rv = client.get('/pnl/alarm-config')
    assert rv.status_code == 200


def test_pnl_upload_rejects_non_xls(client):
    import io
    rv = client.post('/pnl/api/upload',
                     data={'file': (io.BytesIO(b'x'), 'bad.txt')},
                     content_type='multipart/form-data')
    assert rv.status_code == 400
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_pnl_routes.py -v`
Expected: FAIL — 404 (blueprint not registered).

- [ ] **Step 4: Write the blueprint**

```python
# app/blueprints/pnl.py
import os
import datetime
import tempfile
from flask import (Blueprint, render_template, request, jsonify, send_file)
from werkzeug.utils import secure_filename
import db
import queries
import pnl_logic
import pnl_import
from exports.excel_export import timestamped_filename, build_pnl_xlsx

pnl_bp = Blueprint('pnl', __name__, url_prefix='/pnl')

MONTHS_RO = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
             'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
ENTITATI = [('torb', 'Torb Logistic'), ('tobra', 'Tobra Invest'), ('grup', 'Grup consolidat')]


def _severity_class(sev):
    return {'error': 'table-danger', 'warning': 'table-warning',
            'success': 'table-success', 'ok': '', None: ''}.get(sev, '')


@pnl_bp.route('/')
def pnl():
    years = pnl_logic.available_years()
    cy = int(request.args.get('an', datetime.date.today().year))
    py = cy - 1
    entitate = request.args.get('entitate', 'torb')
    show_pct = request.args.get('pct', '0') == '1'

    luni_cy = pnl_logic.compute_pnl_year(entitate, cy)
    luni_cy = sorted(luni_cy.keys())
    luni_py = queries.pnl_available_months(py, entitate)
    data_cy = pnl_logic.compute_pnl_year(entitate, cy)
    data_py = pnl_logic.compute_pnl_year(entitate, py)

    max_luna_cy = max(luni_cy) if luni_cy else 0
    ytd_cy = pnl_logic.compute_ytd(entitate, cy, max_luna_cy) if max_luna_cy else {}
    ytd_py = pnl_logic.compute_ytd(entitate, py, max_luna_cy) if luni_py else {}

    alarm_config = pnl_logic.load_alarm_config()
    alarms = {}
    for luna in luni_cy:
        for _, _label, key in pnl_logic.PNL_STRUCTURE:
            cy_val = data_cy.get(luna, {}).get(key)
            py_val = data_py.get(luna, {}).get(key)
            cfg = alarm_config.get(key, {})
            pct_val = cy_val if key.endswith('%') else None
            a = pnl_logic.compute_alarm(cy_val, py_val, pct_val, cfg)
            trend = pnl_logic.compute_trend_alarm(
                entitate, key, cy, luna, int(cfg.get('alarma_trend_luni', 3) or 3))
            alarms[(luna, key)] = {**a, 'trend': trend}

    return render_template(
        'pnl/pnl.html',
        years=years, cy=cy, py=py, entitate=entitate, entitati=ENTITATI,
        luni_cy=luni_cy, months_ro=MONTHS_RO, structure=pnl_logic.PNL_STRUCTURE,
        data_cy=data_cy, data_py=data_py, ytd_cy=ytd_cy, ytd_py=ytd_py,
        alarms=alarms, show_pct=show_pct, severity_class=_severity_class)


@pnl_bp.route('/import')
def import_page():
    return render_template('pnl/import.html', logs=queries.pnl_import_log(50))


@pnl_bp.route('/api/scan', methods=['POST'])
def api_scan():
    return jsonify({'ok': True, 'results': pnl_import.scan_folders()})


@pnl_bp.route('/api/upload', methods=['POST'])
def api_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'Fișier lipsă'}), 400
    f = request.files['file']
    if not f.filename.lower().endswith('.xls'):
        return jsonify({'error': 'Doar fișiere .xls sunt acceptate'}), 400
    safe_name = secure_filename(f.filename) or 'upload.xls'
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, safe_name)
    f.save(tmp_path)
    try:
        result = pnl_import.import_file(tmp_path)
        result['filename'] = f.filename
    except Exception as e:
        result = {'ok': False, 'rows': 0, 'error': str(e)}
    finally:
        os.unlink(tmp_path)
        os.rmdir(tmp_dir)
    return jsonify(result)


@pnl_bp.route('/alarm-config')
def alarm_config():
    return render_template('pnl/alarm_config.html', rows=queries.pnl_config_rows())


@pnl_bp.route('/api/alarm-config', methods=['POST'])
def api_alarm_config_save():
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    try:
        for row in data.get('rows', []):
            def _f(val):
                return float(val) if val not in (None, '') else None
            conn.execute("""
                INSERT OR REPLACE INTO pnl_config
                (pnl_line, alarma_delta_warn, alarma_delta_err,
                 alarma_prag_warn, alarma_prag_err, alarma_trend_luni, directie)
                VALUES(?,?,?,?,?,?,?)
            """, (
                row.get('pnl_line', ''),
                _f(row.get('delta_warn')), _f(row.get('delta_err')),
                _f(row.get('prag_warn')), _f(row.get('prag_err')),
                int(row.get('trend_luni') or 3),
                row.get('directie', 'sus_bine'),
            ))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'ok': True})


@pnl_bp.route('/export')
def export_pnl():
    an = int(request.args.get('an', datetime.date.today().year))
    buf = build_pnl_xlsx(an)
    return send_file(
        buf, as_attachment=True, download_name=timestamped_filename(f'pnl_{an}'),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
```

Note: Romanian strings (`Fișier lipsă`, `Doar fișiere .xls sunt acceptate`) contain diacritics — before saving, read `docs/TECHNICAL.md` §Encoding and follow its rule.

- [ ] **Step 5: Register the blueprint**

In `app/app.py`, add to the blueprint import block (near line 36):

```python
    from blueprints.pnl import pnl_bp
```

and to the registration block (near line 100):

```python
    app.register_blueprint(pnl_bp)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_pnl_routes.py -v`
Expected: PASS.

- [ ] **Step 7: Lint + commit**

```bash
ruff check app/config.py app/blueprints/pnl.py app/app.py tests/test_pnl_routes.py
git add app/config.py app/blueprints/pnl.py app/app.py tests/test_pnl_routes.py
git commit -m "feat(pnl): config folders + blueprint under /pnl"
```

---

### Task 7: Templates + nav

**Files:**
- Create: `app/templates/pnl/pnl.html`, `app/templates/pnl/import.html`, `app/templates/pnl/alarm_config.html`
- Modify: `app/templates/base.html` (add nav link)
- Test: `tests/test_pnl_routes.py` (extend with content assertions)

**Interfaces:**
- Consumes: template variables produced by Task 6 routes; host `base.html` blocks; `AppError.show()` from `app/static/js/app-error.js`.
- Produces: rendered pages that extend the host layout.

- [ ] **Step 1: Inspect the host base template contract**

Read `app/templates/base.html` and one existing content template (e.g. `app/templates/solduri_neincasate.html`) to learn the exact block names (e.g. `{% block content %}`, `{% block title %}`, script block) and how existing pages call `AppError.show()`.

- [ ] **Step 2: Port the three templates**

Translate the source templates (`pnl_app/templates/{pnl,import,alarm_config}.html`) to extend the host layout:
- Replace `{% extends "base.html" %}` target with the host base and use the host's block names.
- Remove any `<!DOCTYPE>`, `<head>`, Bootstrap CDN links — the host base already loads local Bootstrap + icons.
- Keep the table structure, `ron`/`pct_fmt` formatting (re-register these as Jinja filters on the app, or inline the formatting — see Step 3), entity/year selectors, alarm coloring via `severity_class`.
- In `import.html`, wire upload/scan `fetch` failure branches to `AppError.show(<message>)` instead of inline text.

- [ ] **Step 3: Register the `ron` / `pct_fmt` Jinja filters**

The source registered `@app.template_filter('ron')` and `pct_fmt` on its own app. Add equivalents to the host. Preferred: register on the blueprint via `@pnl_bp.app_template_filter('ron')` / `('pct_fmt')` in `app/blueprints/pnl.py` so they're app-global without touching `app.py`:

```python
@pnl_bp.app_template_filter('ron')
def _fmt_ron(v):
    if v is None:
        return '—'
    try:
        f = float(v)
        if abs(f) >= 1_000_000:
            return f"{f / 1_000_000:.2f}M"
        return f"{int(f):,}".replace(',', '.')
    except (TypeError, ValueError):
        return str(v)


@pnl_bp.app_template_filter('pct_fmt')
def _fmt_pct(v):
    if v is None:
        return '—'
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return str(v)
```

Check no existing global filter named `ron`/`pct_fmt` collides (grep `template_filter` under `app/`); if one exists, reuse it instead.

- [ ] **Step 4: Add the nav link**

In `app/templates/base.html`, after the `reports.profitabilitate` sidebar link, add (match surrounding markup/icon style):

```html
      <a class="sidebar-link{% if request.endpoint == 'pnl.pnl' %} active{% endif %}"
         href="{{ url_for('pnl.pnl') }}" data-label="P&L">
        <i class="bi bi-graph-up-arrow"></i><span>P&L</span></a>
```

- [ ] **Step 5: Extend the route test with content assertions**

```python
def test_pnl_page_renders_structure(client):
    rv = client.get('/pnl')
    assert b'CIFRA DE AFACERI NETA' in rv.data
    assert b'EBITDA' in rv.data


def test_nav_has_pnl_link(client):
    rv = client.get('/pnl')
    assert b'/pnl' in rv.data
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_pnl_routes.py -v`
Expected: PASS (all route + content tests green).

- [ ] **Step 7: Lint + commit**

```bash
ruff check app/blueprints/pnl.py tests/test_pnl_routes.py
git add app/templates/pnl/ app/templates/base.html app/blueprints/pnl.py tests/test_pnl_routes.py
git commit -m "feat(pnl): templates reparented to host layout + nav link"
```

---

### Task 8: Data copy (dev-only) + cutover

**Files:**
- Create (scratchpad, NOT repo): `<scratchpad>/copy_pnl_data.py`
- Delete: `pnl_app/`
- Modify: `CHANGELOG.md`, `context/STATUS.md`, `docs/TECHNICAL.md` (§Data — register the four tables + module)

**Interfaces:**
- Consumes: `pnl_app/pnl.db` (source), `data/torb.db` (target).
- Produces: populated `pnl_*` tables in the local dev DB.

- [ ] **Step 1: Write the one-shot copy script to the scratchpad**

Path: the session scratchpad directory (outside the repo — never committed).

```python
# copy_pnl_data.py  — run ONCE locally in dev, before pushing. Not committed.
import sqlite3

SRC = r"c:\MINE\TorbApp\pnl_app\pnl.db"
DST = r"c:\MINE\TorbApp\data\torb.db"

TABLES = {
    'balante_raw':     'pnl_balante_raw',
    'mapping_conturi': 'pnl_mapping_conturi',
    'pnl_config':      'pnl_config',
    'import_log':      'pnl_import_log',
}

src = sqlite3.connect(SRC)
src.row_factory = sqlite3.Row
dst = sqlite3.connect(DST)

for src_tbl, dst_tbl in TABLES.items():
    rows = src.execute(f"SELECT * FROM {src_tbl}").fetchall()
    if not rows:
        print(f"{src_tbl}: 0 rows, skipped")
        continue
    cols = rows[0].keys()
    placeholders = ",".join("?" * len(cols))
    collist = ",".join(cols)
    dst.executemany(
        f"INSERT OR REPLACE INTO {dst_tbl}({collist}) VALUES({placeholders})",
        [tuple(r) for r in rows])
    dst.commit()
    n = dst.execute(f"SELECT COUNT(*) FROM {dst_tbl}").fetchone()[0]
    print(f"{src_tbl} -> {dst_tbl}: copied {len(rows)}, table now {n}")

src.close()
dst.close()
```

- [ ] **Step 2: Run it once and verify counts**

Run: `python <scratchpad>/copy_pnl_data.py`
Expected: printed per-table copied/total counts matching the source `pnl.db`. Cross-check `balante_raw` count against `SELECT COUNT(*) FROM balante_raw` in `pnl.db`.

- [ ] **Step 3: Manually verify the module against copied data**

Start the app (`Start-Hub.bat` or the documented dev run), log in, open `/pnl`: confirm the year view renders with the copied months, entity switch works, `/pnl/export` downloads a populated workbook. This exercises the real `xlrd`-independent read path end-to-end.

- [ ] **Step 4: Delete the source app**

```bash
git rm -r --cached pnl_app 2>/dev/null || true
rm -rf pnl_app
```

(`pnl_app/` is untracked, so `rm -rf` is the operative step; the `git rm --cached` is a no-op safety net.)

- [ ] **Step 5: Run the full suite + lint**

Run: `python -m pytest -q`
Expected: all pass.
Run: `ruff check .`
Expected: zero errors.

- [ ] **Step 6: Update docs**

- `CHANGELOG.md` `[Unreleased]`: add "P&L module relocated from standalone pnl_app into TorbApp (migration 0028; `/pnl` routes; balante import; styled Excel export)."
- `context/STATUS.md`: reflect completion + next step.
- `docs/TECHNICAL.md` §Data: register the four `pnl_*` tables and the module.

- [ ] **Step 7: Commit**

```bash
git add CHANGELOG.md context/STATUS.md docs/TECHNICAL.md
git commit -m "chore(pnl): cutover - remove pnl_app, update docs"
```

---

## Self-Review

**Spec coverage:** every spec section maps to a task — schema/seed (T1), DB access + queries (T2), compute (T3), import via host xlrd (T4), styled export in shared module (T5), config + namespaced blueprint + auth via registration (T6), reparented templates + nav + AppError (T7), dev-only data copy + cutover + docs (T8). No new deps anywhere; `requirements.txt` untouched.

**Placeholder scan:** no TBD/TODO; every code step carries complete code. Template porting (T7 Step 2) is the one translate-from-source step — bounded by the source files + explicit block/CDN/AppError instructions, not a placeholder.

**Type consistency:** `queries.pnl_*` signatures defined in T2 are consumed unchanged in T3/T6; `build_pnl_xlsx(an)` defined T5 consumed T6; `pnl_import.import_file/scan_folders/persist_rows` defined T4 consumed T6; `pnl_bp` under `/pnl` consistent T6/T7. `compute_pnl_year` returns `{luna: dict}` — callers use `.keys()` then `sorted()`, consistent.

**Known deferrals:** end-to-end real-`.xls` xlrd read is verified manually at cutover (T8 Step 3) rather than by a hermetic unit test, because writing a legacy `.xls` fixture needs `xlwt` (not a host dep). Import logic is unit-tested via `persist_rows` + `parse_period`/`detect_entity` (T4); the xlrd read wrapper is thin and matches the proven host pattern in `app/supplier_offer.py`.
