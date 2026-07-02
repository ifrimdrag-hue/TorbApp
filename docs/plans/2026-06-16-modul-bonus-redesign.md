# Modul Bonus Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Înlocuiește modulul de bonus hardcodat (`PRESETS`) cu un sistem config-driven, salvat în DB, unde directorul comercial setează lunar obiective KPI configurabile (vânzări, marjă, game individuale, nr. clienți, clienți noi/gamă, încasări, scriptic) per agent, cu ponderi și valoare de bonus proprii, plus flux de închidere a lunii.

**Architecture:** Reutilizează schema DB dormantă (`bonus_config`, `bonus_lunar_config`, `bonus_obiective_strategice`, `bonus_payout_grid`, `bonus_istoric`), formalizată acum într-o migrație versionată. Logica de calcul din `app/bonus_calc.py` devine config-driven (iterează rânduri KPI generice + grilă de payout din DB). Query-urile noi trăiesc în `app/queries/bonus.py`. Rutele și 5 template-uri trăiesc în blueprint-ul `bonus`.

**Tech Stack:** Python 3.14, Flask, SQLite (sqlite3 + `app/db.py`), Jinja2, Bootstrap 5, Chart.js, openpyxl (export), pytest.

**Referință design:** `docs/superpowers/specs/2026-06-16-modul-bonus-redesign-design.md`

**Reguli proiect (citește înainte):**
- `ruff check .` trebuie să treacă (zero erori). Hook PostToolUse rulează `ruff --fix` automat.
- Encoding românesc pentru `.py` — vezi `.claude/project_knowledge.md`.
- ETL/scripturi se rulează din root. Testele construiesc schema DOAR din migrații (`tests/conftest.py` → `migrations/runner.run_all`).
- Nu adăuga `.py` în root. Migrații în `migrations/`, query-uri în `app/queries/`, rute în `app/blueprints/`.

---

## File Structure

**Create:**
- `migrations/0011_20260616_bonus_redesign.py` — DDL idempotent pt. tabelele bonus + coloană `realizat_manual` + seed (grilă `_default`, 4 agenți de teren, ștergere Teo).
- `app/templates/bonus/obiective.html` — setare obiective (varianta C).
- `app/templates/bonus/inchidere.html` — închidere lună.
- `app/templates/bonus/config.html` — management agenți.
- `app/templates/bonus/clienti_noi_gama.html` — drill-down clienți noi pe gamă.
- `tests/test_bonus_queries.py` — teste query layer.
- `tests/test_bonus_routes.py` — teste integrare rute.

**Modify:**
- `app/bonus_calc.py` — adaugă motor config-driven (`payout_multiplier(score, grid)`, `calc_kpi`, `calc_agent_month`). Păstrează `PAYOUT_GRID`, `MONTHS_RO`, `SIM_MONTHS`, `STRATEGIC_BRANDS` pt. compat.
- `app/queries/bonus.py` — extinde masiv (config readers/writers, realizat auto, clienți noi/gamă, istoric).
- `app/queries/__init__.py` — re-export noile funcții din `queries.bonus`.
- `app/blueprints/bonus.py` — rebuild rute tracker + obiective + închidere + config + drill-down; adaptează export.
- `app/templates/bonus.html` — rebuild tracker (citește din DB).

**Untouched:** `app/templates/team.html`, `app/blueprints/analytics.py` (tracker echipă), modelul paralel `targeturi_kpi`/`actuale_kpi`.

---

## Convenții de date (folosite în tot planul)

KPI row (dict) — forma canonică pasată motorului și salvată:
```python
{
  "tip": "vanzari" | "marja" | "brand" | "clienti" | "clienti_noi_gama" | "incasari" | "scriptic",
  "referinta": str | None,     # numele gamei pt. brand/clienti_noi_gama; textul obiectivului pt. scriptic
  "target": float,             # target_valoare
  "unitate": "ron" | "nr" | "pct",
  "pondere": float,            # 0..1 (în DB), afișat ca % în UI
  "actual": float,             # realizat (auto sau manual); completat la calcul
}
```

`bonus_config.db_agent` poate conține mai mulți agenți separați prin `|` (ex. online). Filtrarea pe `tranzactii.agent` folosește un helper `_agent_in(db_agent)` care produce `LOWER(agent) IN (...)`.

---

## Phase 0 — Schema foundation

### Task 1: Migrație 0011 — tabele bonus + coloană nouă + seed

**Files:**
- Create: `migrations/0011_20260616_bonus_redesign.py`
- Test: `tests/test_bonus_queries.py` (doar testul de schemă în acest task)

- [ ] **Step 1: Scrie migrația**

Create `migrations/0011_20260616_bonus_redesign.py`:

```python
"""
Migration 0011 — bonus module redesign schema.

Formalizează tabelele bonus (create anterior ad-hoc, doar în data/torb.db) în
runner-ul versionat, ca testele și deploy-urile noi să le aibă. Idempotent.

Creează (IF NOT EXISTS): bonus_config, bonus_lunar_config,
        bonus_obiective_strategice, bonus_payout_grid, bonus_istoric
Adaugă:  coloana realizat_manual pe bonus_obiective_strategice
Seed:    grila _default, cei 4 agenți de teren; șterge Teo dacă există.
"""

VERSION = 11
NAME = "0011_20260616_bonus_redesign"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS bonus_config (
            agent_key   TEXT PRIMARY KEY,
            db_agent    TEXT,
            tip_agent   TEXT DEFAULT 'field',
            w_sales     REAL DEFAULT 0.45,
            w_margin    REAL DEFAULT 0.25,
            w_strategic REAL DEFAULT 0.30,
            gate_sales  REAL DEFAULT 0.80,
            gate_margin REAL DEFAULT 0.80,
            growth_pct  REAL DEFAULT 0.20,
            activ       INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS bonus_lunar_config (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            an            INTEGER NOT NULL,
            luna          INTEGER NOT NULL,
            agent_key     TEXT NOT NULL,
            monthly_bonus REAL NOT NULL,
            pool_listari  REAL DEFAULT 0,
            w_sales       REAL,
            w_margin      REAL,
            w_strategic   REAL,
            gate_sales    REAL,
            gate_margin   REAL,
            growth_pct    REAL,
            UNIQUE(an, luna, agent_key)
        );

        CREATE TABLE IF NOT EXISTS bonus_obiective_strategice (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            an             INTEGER NOT NULL,
            luna           INTEGER NOT NULL,
            agent_key      TEXT NOT NULL,
            tip            TEXT NOT NULL,
            referinta      TEXT,
            target_valoare REAL,
            target_unitate TEXT DEFAULT 'ron',
            pondere        REAL DEFAULT 0,
            bonus_per_unit REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS bonus_payout_grid (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_key   TEXT NOT NULL,
            threshold   REAL NOT NULL,
            multiplier  REAL NOT NULL,
            UNIQUE(agent_key, threshold)
        );

        CREATE TABLE IF NOT EXISTS bonus_istoric (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            an             INTEGER NOT NULL,
            luna           INTEGER NOT NULL,
            agent_key      TEXT NOT NULL,
            lunar_data     TEXT,
            penalty_pct    REAL DEFAULT 0,
            grad_incasare  REAL DEFAULT 1.0,
            stare          TEXT DEFAULT 'deschis',
            inchis_la      TEXT,
            note           TEXT,
            UNIQUE(an, luna, agent_key)
        );
    """)

    # Coloană nouă (idempotent — verifică înainte de ALTER)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bonus_obiective_strategice)")}
    if "realizat_manual" not in cols:
        conn.execute("ALTER TABLE bonus_obiective_strategice ADD COLUMN realizat_manual REAL")

    # Seed grila _default
    grid = [(0.0, 0.0), (0.80, 0.5), (0.95, 0.8), (1.00, 1.0),
            (1.02, 1.1), (1.10, 1.2), (1.20, 1.5)]
    for thr, mul in grid:
        conn.execute(
            "INSERT OR IGNORE INTO bonus_payout_grid (agent_key, threshold, multiplier) "
            "VALUES ('_default', ?, ?)", (thr, mul))

    # Seed cei 4 agenți de teren (idempotent)
    agents = [
        ("Claudiu", "BRINZA CLAUDIU",   0.45, 0.25, 0.30),
        ("Bogdan",  "DRAGNEA BOGDAN",   0.50, 0.25, 0.25),
        ("Oana",    "Oana Filip",       0.50, 0.20, 0.30),
        ("Ionut",   "CONSTANTIN IONUT", 0.50, 0.20, 0.30),
    ]
    for key, db_agent, ws, wm, wst in agents:
        conn.execute(
            "INSERT OR IGNORE INTO bonus_config "
            "(agent_key, db_agent, tip_agent, w_sales, w_margin, w_strategic, "
            " gate_sales, gate_margin, growth_pct, activ) "
            "VALUES (?, ?, 'field', ?, ?, ?, 0.80, 0.80, 0.20, 1)",
            (key, db_agent, ws, wm, wst))

    # Teo eliminat complet din toate tabelele bonus
    for tbl in ("bonus_config", "bonus_lunar_config",
                "bonus_obiective_strategice", "bonus_payout_grid", "bonus_istoric"):
        conn.execute(f"DELETE FROM {tbl} WHERE agent_key = 'Teo'")
```

- [ ] **Step 2: Aplică migrația pe DB-ul viu și verifică**

Run: `python migrations/runner.py data/torb.db`
Expected: `Applying 0011: 0011_20260616_bonus_redesign ...` apoi `Done`. Rulează din nou → `DB schema is up to date.` (idempotent).

- [ ] **Step 3: Verifică Teo eliminat și agenții prezenți**

Run:
```bash
python -c "import sqlite3; c=sqlite3.connect('data/torb.db'); print(sorted(r[0] for r in c.execute('SELECT agent_key FROM bonus_config')))"
```
Expected: `['Bogdan', 'Claudiu', 'Ionut', 'Oana']` (fără Teo; `Online` poate exista din seed-ul vechi — acceptabil, e dezactivabil din UI).

- [ ] **Step 4: Scrie testul de schemă**

Create `tests/test_bonus_queries.py`:
```python
"""Tests for bonus DB schema and query layer (app/queries/bonus.py)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from db import query


def test_bonus_tables_exist():
    names = {r['name'] for r in query(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'bonus_config', 'bonus_lunar_config', 'bonus_obiective_strategice',
            'bonus_payout_grid', 'bonus_istoric'} <= names


def test_realizat_manual_column_exists():
    cols = {r['name'] for r in query("PRAGMA table_info(bonus_obiective_strategice)")}
    assert 'realizat_manual' in cols


def test_default_payout_grid_seeded():
    rows = query("SELECT threshold, multiplier FROM bonus_payout_grid "
                 "WHERE agent_key='_default' ORDER BY threshold")
    assert (rows[0]['threshold'], rows[0]['multiplier']) == (0.0, 0.0)
    assert (rows[-1]['threshold'], rows[-1]['multiplier']) == (1.2, 1.5)
```

- [ ] **Step 5: Rulează testele**

Run: `python -m pytest tests/test_bonus_queries.py -v`
Expected: 3 PASS (conftest construiește schema din migrații, deci tabelele există).

- [ ] **Step 6: Commit**

```bash
git add migrations/0011_20260616_bonus_redesign.py tests/test_bonus_queries.py
git commit -m "feat(bonus): migratie 0011 — tabele bonus versionate + seed agenti teren"
```

---

## Phase 1 — Motor de calcul config-driven (pur, TDD)

### Task 2: `payout_multiplier(score, grid)` cu grilă parametrizabilă

**Files:**
- Modify: `app/bonus_calc.py`
- Test: `tests/test_bonus_calc.py`

- [ ] **Step 1: Scrie testele care pică**

Adaugă în `tests/test_bonus_calc.py` (după importuri, adaugă `calc_kpi, calc_agent_month` la import din `bonus_calc`):
```python
_GRID = [(0.0, 0.0), (0.80, 0.5), (0.95, 0.8), (1.00, 1.0),
         (1.02, 1.1), (1.10, 1.2), (1.20, 1.5)]

def test_payout_with_explicit_grid():
    from bonus_calc import payout_multiplier
    assert payout_multiplier(0.79, _GRID) == 0.0
    assert payout_multiplier(0.80, _GRID) == 0.5
    assert payout_multiplier(1.50, _GRID) == 1.5

def test_payout_default_grid_backward_compat():
    from bonus_calc import payout_multiplier
    assert payout_multiplier(0.80) == 0.5  # fără grid → folosește PAYOUT_GRID
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_calc.py::test_payout_with_explicit_grid -v`
Expected: FAIL (`payout_multiplier()` ia un singur argument).

- [ ] **Step 3: Modifică `payout_multiplier`**

În `app/bonus_calc.py` înlocuiește funcția existentă:
```python
def payout_multiplier(score: float, grid: list | None = None) -> float:
    g = grid if grid is not None else PAYOUT_GRID
    result = g[0][1]
    for threshold, multiplier in g:
        if score >= threshold:
            result = multiplier
        else:
            break
    return result
```

- [ ] **Step 4: Rulează → trece**

Run: `python -m pytest tests/test_bonus_calc.py -v`
Expected: toate PASS (inclusiv testele vechi cu un singur argument).

- [ ] **Step 5: Commit**

```bash
git add app/bonus_calc.py tests/test_bonus_calc.py
git commit -m "feat(bonus): payout_multiplier accepta grila parametrizabila"
```

### Task 3: `calc_kpi` și `calc_agent_month` (motor generic pe rânduri KPI)

**Files:**
- Modify: `app/bonus_calc.py`
- Test: `tests/test_bonus_calc.py`

- [ ] **Step 1: Scrie testele care pică**

Adaugă în `tests/test_bonus_calc.py`:
```python
def test_calc_kpi_gated_below_80():
    from bonus_calc import calc_kpi
    r = calc_kpi({"tip": "vanzari", "target": 100.0, "actual": 79.0, "pondere": 0.5}, _GRID)
    assert r["realizare"] == 0.79
    assert r["multiplier"] == 0.0
    assert r["weighted"] == 0.0

def test_calc_kpi_at_target():
    from bonus_calc import calc_kpi
    r = calc_kpi({"tip": "vanzari", "target": 100.0, "actual": 100.0, "pondere": 0.5}, _GRID)
    assert r["realizare"] == 1.0
    assert r["multiplier"] == 1.0
    assert r["weighted"] == 0.5

def test_calc_kpi_zero_target_is_zero():
    from bonus_calc import calc_kpi
    r = calc_kpi({"tip": "incasari", "target": 0.0, "actual": 50.0, "pondere": 0.3}, _GRID)
    assert r["realizare"] == 0.0
    assert r["weighted"] == 0.0

def test_calc_agent_month_sums_weighted_bonus():
    from bonus_calc import calc_agent_month
    kpis = [
        {"tip": "vanzari", "target": 100.0, "actual": 100.0, "pondere": 0.6},  # 1.0x → 0.6
        {"tip": "marja",   "target": 100.0, "actual": 120.0, "pondere": 0.4},  # 1.5x → 0.6
    ]
    out = calc_agent_month(4000.0, 0.0, kpis, _GRID)
    # scor ponderat = 0.6*1.0 + 0.4*1.5 = 1.2 ; bonus = 4000*1.2 = 4800
    assert out["scor"] == 1.2
    assert out["total_bonus"] == 4800.0
    assert out["kpis"][0]["bonus"] == 2400.0   # 4000*0.6*1.0
    assert out["kpis"][1]["bonus"] == 2400.0   # 4000*0.4*1.5

def test_calc_agent_month_penalty():
    from bonus_calc import calc_agent_month
    kpis = [{"tip": "vanzari", "target": 100.0, "actual": 100.0, "pondere": 1.0}]
    out = calc_agent_month(1000.0, 0.10, kpis, _GRID)
    assert out["total_bonus"] == 900.0  # 1000*1.0*1.0*(1-0.10)
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_calc.py::test_calc_agent_month_sums_weighted_bonus -v`
Expected: FAIL (`calc_agent_month` nu există).

- [ ] **Step 3: Implementează motorul**

Adaugă în `app/bonus_calc.py`:
```python
def calc_kpi(kpi: dict, grid: list | None = None) -> dict:
    """Calculează realizarea și multiplicatorul pentru un singur rând KPI.

    kpi: {tip, target, actual, pondere}
    Returnează kpi-ul augmentat cu realizare, multiplier, weighted.
    """
    target = kpi.get("target") or 0.0
    actual = kpi.get("actual") or 0.0
    pondere = kpi.get("pondere") or 0.0
    realizare = (actual / target) if target else 0.0
    multiplier = payout_multiplier(realizare, grid)
    weighted = pondere * multiplier
    return {
        **kpi,
        "realizare": round(realizare, 4),
        "multiplier": multiplier,
        "weighted": round(weighted, 4),
    }


def calc_agent_month(monthly_bonus: float, penalty: float,
                     kpis: list, grid: list | None = None) -> dict:
    """Calculează bonusul lunar al unui agent din lista de rânduri KPI.

    bonus = monthly_bonus * Σ(pondere_i * multiplier_i) * (1 - penalty)
    """
    factor = 1.0 - (penalty or 0.0)
    calc_rows = []
    scor = 0.0
    for k in kpis:
        r = calc_kpi(k, grid)
        r["bonus"] = round((monthly_bonus or 0.0) * r["weighted"] * factor, 2)
        scor += r["weighted"]
        calc_rows.append(r)
    return {
        "kpis": calc_rows,
        "scor": round(scor, 4),
        "total_pondere": round(sum((k.get("pondere") or 0.0) for k in kpis), 4),
        "total_bonus": round((monthly_bonus or 0.0) * scor * factor, 2),
    }
```

- [ ] **Step 4: Rulează → trece**

Run: `python -m pytest tests/test_bonus_calc.py -v`
Expected: toate PASS.

- [ ] **Step 5: Commit**

```bash
git add app/bonus_calc.py tests/test_bonus_calc.py
git commit -m "feat(bonus): motor config-driven calc_kpi + calc_agent_month"
```

---

## Phase 2 — Query layer (`app/queries/bonus.py`)

### Task 4: Config readers + helper filtru agent

**Files:**
- Modify: `app/queries/bonus.py`, `app/queries/__init__.py`
- Test: `tests/test_bonus_queries.py`

- [ ] **Step 1: Scrie testele care pică**

Adaugă în `tests/test_bonus_queries.py`:
```python
def test_bonus_agents_returns_field_agents():
    from queries.bonus import bonus_agents
    keys = {a['agent_key'] for a in bonus_agents()}
    assert {'Bogdan', 'Claudiu', 'Oana', 'Ionut'} <= keys
    assert 'Teo' not in keys

def test_payout_grid_falls_back_to_default():
    from queries.bonus import payout_grid
    g = payout_grid('AgentInexistent')
    assert g[0] == (0.0, 0.0)
    assert g[-1] == (1.2, 1.5)
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_queries.py::test_bonus_agents_returns_field_agents -v`
Expected: FAIL (ImportError: `bonus_agents`).

- [ ] **Step 3: Implementează în `app/queries/bonus.py`**

Înlocuiește conținutul fișierului cu (păstrând `bonus_team`):
```python
from db import query, get_db


def _write(sql, params=None):
    """Execută un singur statement de scriere (INSERT/UPDATE/DELETE) cu commit.

    Proiectul nu are un helper de scriere în db.py — scrierile folosesc get_db()
    (conexiune nouă; caller-ul face commit + close). Vezi app/queries/export.py.
    """
    db = get_db()
    try:
        db.execute(sql, params or {})
        db.commit()
    finally:
        db.close()


def _agent_in(db_agent):
    """Construiește un filtru SQL pe tranzactii.agent dintr-un db_agent care
    poate conține mai mulți agenți separați prin '|' (ex. online).
    Returnează (fragment_sql, params_dict)."""
    parts = [p.strip() for p in (db_agent or "").split("|") if p.strip()]
    if not parts:
        return ("1=0", {})
    keys = [f"a{i}" for i in range(len(parts))]
    frag = "LOWER(agent) IN (" + ",".join(f"LOWER(:{k})" for k in keys) + ")"
    return (frag, {k: v for k, v in zip(keys, parts)})


def bonus_team():
    return query("""
        SELECT employee_id, nume, rol, activ,
            bonus_target_lunar_ron, bonus_target_trim_ron, observatii
        FROM echipa WHERE activ = 1
        ORDER BY bonus_target_lunar_ron DESC
    """)


def bonus_agents(activ_only=True):
    sql = ("SELECT agent_key, db_agent, tip_agent, growth_pct, activ "
           "FROM bonus_config")
    if activ_only:
        sql += " WHERE activ = 1"
    sql += " ORDER BY agent_key"
    return query(sql)


def lunar_config(an, luna, agent_key):
    rows = query(
        "SELECT monthly_bonus, growth_pct FROM bonus_lunar_config "
        "WHERE an=:an AND luna=:luna AND agent_key=:k",
        {"an": an, "luna": luna, "k": agent_key})
    return rows[0] if rows else None


def obiective(an, luna, agent_key):
    return query(
        "SELECT id, tip, referinta, target_valoare AS target, target_unitate AS unitate, "
        "       pondere, realizat_manual "
        "FROM bonus_obiective_strategice "
        "WHERE an=:an AND luna=:luna AND agent_key=:k "
        "ORDER BY id",
        {"an": an, "luna": luna, "k": agent_key})


def payout_grid(agent_key):
    rows = query(
        "SELECT threshold, multiplier FROM bonus_payout_grid "
        "WHERE agent_key=:k ORDER BY threshold", {"k": agent_key})
    if not rows:
        rows = query(
            "SELECT threshold, multiplier FROM bonus_payout_grid "
            "WHERE agent_key='_default' ORDER BY threshold")
    return [(r["threshold"], r["multiplier"]) for r in rows]
```

- [ ] **Step 4: Verifică helperele de DB**

Run: `python -c "import sys; sys.path.insert(0,'app'); from db import query, get_db; print('ok')"`
Expected: `ok`. (Scrierile din task-urile următoare folosesc `_write()` definit mai sus, care se bazează pe `get_db()` — pattern confirmat în `app/queries/export.py`.)

- [ ] **Step 5: Re-export în `app/queries/__init__.py`**

Adaugă după blocul existent care importă din `queries.bonus` (caută `bonus_team`); dacă nu există un astfel de bloc, adaugă:
```python
from queries.bonus import (
    bonus_team as bonus_team,
    bonus_agents as bonus_agents,
    lunar_config as lunar_config,
    obiective as obiective,
    payout_grid as payout_grid,
)
```

- [ ] **Step 6: Rulează → trece**

Run: `python -m pytest tests/test_bonus_queries.py -v`
Expected: toate PASS.

- [ ] **Step 7: Commit**

```bash
git add app/queries/bonus.py app/queries/__init__.py tests/test_bonus_queries.py
git commit -m "feat(bonus): query layer config readers + payout grid fallback"
```

### Task 5: Realizat auto + baseline PY (vânzări, marjă, brand, clienți)

**Files:**
- Modify: `app/queries/bonus.py`, `app/queries/__init__.py`
- Test: `tests/test_bonus_queries.py`

> Notă seed test: `tests/conftest.py` are deja câteva tranzacții minime. Pentru aceste teste, inserăm tranzacții deterministe într-o fixtură locală.

- [ ] **Step 1: Scrie testele care pică**

Adaugă în `tests/test_bonus_queries.py`:
```python
import sqlite3
import paths
import pytest

@pytest.fixture
def seed_tx():
    """Inserează tranzacții deterministe pentru un agent de test și curăță după."""
    conn = sqlite3.connect(paths.DB_PATH)
    rows = [
        # an, luna, data_dl, agent, furnizor, client, cod_client, val_neta, marja_bruta
        (2025, 6, '2025-06-10', 'TESTAGENT', 'Basilur', 'Client A', 'CA', 1000.0, 300.0),
        (2025, 6, '2025-06-12', 'TESTAGENT', 'Toras',   'Client B', 'CB', 500.0,  100.0),
        (2026, 6, '2026-06-10', 'TESTAGENT', 'Basilur', 'Client A', 'CA', 1200.0, 400.0),
        (2026, 6, '2026-06-11', 'TESTAGENT', 'Basilur', 'Client C', 'CC', 800.0,  200.0),
    ]
    conn.executemany(
        "INSERT INTO tranzactii (an, luna, data_dl, agent, furnizor, client, "
        "cod_client, val_neta, marja_bruta) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(paths.DB_PATH)
    conn.execute("DELETE FROM tranzactii WHERE agent='TESTAGENT'")
    conn.commit()
    conn.close()


def test_realizat_auto_vanzari_marja(seed_tx):
    from queries.bonus import realizat_auto
    r = realizat_auto('TESTAGENT', 2026, 6)
    assert r['vanzari'] == 2000.0   # 1200 + 800
    assert r['marja'] == 600.0      # 400 + 200
    assert r['clienti'] == 2        # Client A, Client C

def test_realizat_brand(seed_tx):
    from queries.bonus import realizat_brand
    assert realizat_brand('TESTAGENT', 'Basilur', 2026, 6) == 2000.0

def test_py_baseline_same_month(seed_tx):
    from queries.bonus import py_baseline
    b = py_baseline('TESTAGENT', 2026, 6)  # se uită la 2025-06
    assert b['vanzari'] == 1500.0   # 1000 + 500
    assert b['brand']['Basilur'] == 1000.0
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_queries.py::test_realizat_auto_vanzari_marja -v`
Expected: FAIL (ImportError: `realizat_auto`).

- [ ] **Step 3: Implementează în `app/queries/bonus.py`**

Adaugă:
```python
def realizat_auto(db_agent, an, luna):
    """Realizat lunar auto din tranzactii: vânzări, marjă, nr. clienți activi."""
    frag, params = _agent_in(db_agent)
    params.update({"an": an, "luna": luna})
    rows = query(
        f"SELECT COALESCE(SUM(val_neta),0) AS vanzari, "
        f"       COALESCE(SUM(marja_bruta),0) AS marja, "
        f"       COUNT(DISTINCT cod_client) AS clienti "
        f"FROM tranzactii WHERE {frag} AND an=:an AND luna=:luna", params)
    r = rows[0]
    return {"vanzari": r["vanzari"], "marja": r["marja"], "clienti": r["clienti"]}


def realizat_brand(db_agent, furnizor, an, luna):
    frag, params = _agent_in(db_agent)
    params.update({"an": an, "luna": luna, "f": furnizor})
    rows = query(
        f"SELECT COALESCE(SUM(val_neta),0) AS vn FROM tranzactii "
        f"WHERE {frag} AND furnizor=:f AND an=:an AND luna=:luna", params)
    return rows[0]["vn"]


def py_baseline(db_agent, an, luna):
    """Baseline anul trecut aceeași lună: vânzări, marjă, clienți + per-brand."""
    py = an - 1
    base = realizat_auto(db_agent, py, luna)
    frag, params = _agent_in(db_agent)
    params.update({"an": py, "luna": luna})
    brand_rows = query(
        f"SELECT furnizor, COALESCE(SUM(val_neta),0) AS vn FROM tranzactii "
        f"WHERE {frag} AND an=:an AND luna=:luna GROUP BY furnizor", params)
    base["brand"] = {r["furnizor"]: r["vn"] for r in brand_rows}
    return base
```

- [ ] **Step 4: Re-export în `app/queries/__init__.py`**

Adaugă la blocul `from queries.bonus import (...)`:
```python
    realizat_auto as realizat_auto,
    realizat_brand as realizat_brand,
    py_baseline as py_baseline,
```

- [ ] **Step 5: Rulează → trece**

Run: `python -m pytest tests/test_bonus_queries.py -v`
Expected: toate PASS.

- [ ] **Step 6: Commit**

```bash
git add app/queries/bonus.py app/queries/__init__.py tests/test_bonus_queries.py
git commit -m "feat(bonus): realizat auto + baseline PY same-month"
```

### Task 6: KPI `clienti_noi_gama` — count + listă drill-down

**Files:**
- Modify: `app/queries/bonus.py`, `app/queries/__init__.py`
- Test: `tests/test_bonus_queries.py`

- [ ] **Step 1: Scrie testele care pică**

Adaugă în `tests/test_bonus_queries.py`:
```python
@pytest.fixture
def seed_tx_noi():
    """Client D fără istoric Basilur în 24 luni; Client A cu istoric → nu e nou."""
    conn = sqlite3.connect(paths.DB_PATH)
    rows = [
        (2024, 1,  '2024-01-15', 'NAGENT', 'Basilur', 'Client A', 'NA', 500.0, 100.0),
        (2026, 6,  '2026-06-10', 'NAGENT', 'Basilur', 'Client A', 'NA', 600.0, 150.0),
        (2026, 6,  '2026-06-11', 'NAGENT', 'Basilur', 'Client D', 'ND', 700.0, 200.0),
    ]
    conn.executemany(
        "INSERT INTO tranzactii (an, luna, data_dl, agent, furnizor, client, "
        "cod_client, val_neta, marja_bruta) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit(); conn.close()
    yield
    conn = sqlite3.connect(paths.DB_PATH)
    conn.execute("DELETE FROM tranzactii WHERE agent='NAGENT'")
    conn.commit(); conn.close()


def test_clienti_noi_gama_count(seed_tx_noi):
    from queries.bonus import clienti_noi_gama_count
    # Client A a cumpărat Basilur în 2024-01 (în fereastra de 24 luni înainte de 2026-06) → nu e nou
    # Client D nu are istoric Basilur → e nou
    assert clienti_noi_gama_count('NAGENT', 'Basilur', 2026, 6) == 1

def test_clienti_noi_gama_list(seed_tx_noi):
    from queries.bonus import clienti_noi_gama_list
    rows = clienti_noi_gama_list('NAGENT', 'Basilur', 2026, 6)
    assert [r['cod_client'] for r in rows] == ['ND']
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_queries.py::test_clienti_noi_gama_count -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implementează în `app/queries/bonus.py`**

Adaugă:
```python
_NOI_GAMA_CTE = """
WITH luna_clienti AS (
  SELECT DISTINCT cod_client, client FROM tranzactii
  WHERE {frag} AND furnizor=:gama AND an=:an AND luna=:luna
)
SELECT {select}
FROM luna_clienti lc
WHERE NOT EXISTS (
  SELECT 1 FROM tranzactii t2
  WHERE t2.cod_client = lc.cod_client AND t2.furnizor = :gama
    AND t2.data_dl >= date(:month_start, '-24 months')
    AND t2.data_dl <  :month_start
)
"""


def _noi_gama_params(db_agent, gama, an, luna):
    frag, params = _agent_in(db_agent)
    params.update({"gama": gama, "an": an, "luna": luna,
                   "month_start": f"{an}-{luna:02d}-01"})
    return frag, params


def clienti_noi_gama_count(db_agent, gama, an, luna):
    frag, params = _noi_gama_params(db_agent, gama, an, luna)
    sql = _NOI_GAMA_CTE.format(frag=frag, select="COUNT(*) AS n")
    return query(sql, params)[0]["n"]


def clienti_noi_gama_list(db_agent, gama, an, luna):
    frag, params = _noi_gama_params(db_agent, gama, an, luna)
    sql = _NOI_GAMA_CTE.format(frag=frag, select="lc.cod_client, lc.client")
    sql += " ORDER BY lc.client"
    return query(sql, params)
```

- [ ] **Step 4: Re-export în `app/queries/__init__.py`**

Adaugă la blocul `from queries.bonus import (...)`:
```python
    clienti_noi_gama_count as clienti_noi_gama_count,
    clienti_noi_gama_list as clienti_noi_gama_list,
```

- [ ] **Step 5: Rulează → trece**

Run: `python -m pytest tests/test_bonus_queries.py -v`
Expected: toate PASS.

- [ ] **Step 6: Commit**

```bash
git add app/queries/bonus.py app/queries/__init__.py tests/test_bonus_queries.py
git commit -m "feat(bonus): KPI clienti noi pe gama (count + lista drill-down)"
```

### Task 7: Writers — salvare obiective, management agenți, istoric (închidere)

**Files:**
- Modify: `app/queries/bonus.py`, `app/queries/__init__.py`
- Test: `tests/test_bonus_queries.py`

- [ ] **Step 1: Scrie testele care pică**

Adaugă în `tests/test_bonus_queries.py`:
```python
def test_save_and_read_obiective():
    from queries.bonus import save_obiective, obiective, lunar_config
    kpis = [
        {"tip": "vanzari", "referinta": None, "target": 100000.0, "unitate": "ron", "pondere": 0.5},
        {"tip": "brand", "referinta": "Basilur", "target": 30000.0, "unitate": "ron", "pondere": 0.5},
    ]
    save_obiective(2026, 7, 'Bogdan', monthly_bonus=4000.0, growth_pct=0.20, kpis=kpis)
    cfg = lunar_config(2026, 7, 'Bogdan')
    assert cfg['monthly_bonus'] == 4000.0
    rows = obiective(2026, 7, 'Bogdan')
    assert len(rows) == 2
    assert {r['tip'] for r in rows} == {'vanzari', 'brand'}

def test_save_obiective_replaces_existing():
    from queries.bonus import save_obiective, obiective
    save_obiective(2026, 8, 'Oana', 3000.0, 0.20,
                   [{"tip": "vanzari", "referinta": None, "target": 1.0, "unitate": "ron", "pondere": 1.0}])
    save_obiective(2026, 8, 'Oana', 3000.0, 0.20,
                   [{"tip": "marja", "referinta": None, "target": 2.0, "unitate": "ron", "pondere": 1.0}])
    rows = obiective(2026, 8, 'Oana')
    assert len(rows) == 1 and rows[0]['tip'] == 'marja'

def test_istoric_lock_and_get():
    from queries.bonus import istoric_lock, istoric_get
    istoric_lock(2026, 5, 'Bogdan', lunar_data='{"x":1}', penalty=0.0,
                 grad_incasare=1.0, note='test')
    rec = istoric_get(2026, 5, 'Bogdan')
    assert rec['stare'] == 'inchis'
    assert rec['lunar_data'] == '{"x":1}'

def test_add_and_disable_agent():
    from queries.bonus import add_agent, set_agent_active, bonus_agents
    add_agent('Online', 'EMAG|SITE|TRENDYOL', tip_agent='online')
    assert 'Online' in {a['agent_key'] for a in bonus_agents()}
    set_agent_active('Online', 0)
    assert 'Online' not in {a['agent_key'] for a in bonus_agents(activ_only=True)}
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_queries.py::test_save_and_read_obiective -v`
Expected: FAIL (ImportError: `save_obiective`).

- [ ] **Step 3: Implementează în `app/queries/bonus.py`**

Adaugă:
```python
def save_obiective(an, luna, agent_key, monthly_bonus, growth_pct, kpis):
    """Upsert config lunar + înlocuiește toate rândurile KPI pentru (an,luna,agent).

    Folosește o singură conexiune pentru a face delete+insert tranzacțional.
    """
    db = get_db()
    try:
        db.execute(
            "INSERT INTO bonus_lunar_config (an, luna, agent_key, monthly_bonus, growth_pct) "
            "VALUES (:an,:luna,:k,:mb,:g) "
            "ON CONFLICT(an,luna,agent_key) DO UPDATE SET "
            "  monthly_bonus=excluded.monthly_bonus, growth_pct=excluded.growth_pct",
            {"an": an, "luna": luna, "k": agent_key, "mb": monthly_bonus, "g": growth_pct})
        db.execute(
            "DELETE FROM bonus_obiective_strategice "
            "WHERE an=:an AND luna=:luna AND agent_key=:k",
            {"an": an, "luna": luna, "k": agent_key})
        for kpi in kpis:
            db.execute(
                "INSERT INTO bonus_obiective_strategice "
                "(an, luna, agent_key, tip, referinta, target_valoare, target_unitate, "
                " pondere, realizat_manual) "
                "VALUES (:an,:luna,:k,:tip,:ref,:tv,:un,:pond,:rm)",
                {"an": an, "luna": luna, "k": agent_key,
                 "tip": kpi["tip"], "ref": kpi.get("referinta"),
                 "tv": kpi.get("target"), "un": kpi.get("unitate", "ron"),
                 "pond": kpi.get("pondere", 0), "rm": kpi.get("realizat_manual")})
        db.commit()
    finally:
        db.close()


def istoric_get(an, luna, agent_key):
    rows = query(
        "SELECT lunar_data, penalty_pct, grad_incasare, stare, inchis_la, note "
        "FROM bonus_istoric WHERE an=:an AND luna=:luna AND agent_key=:k",
        {"an": an, "luna": luna, "k": agent_key})
    return rows[0] if rows else None


def istoric_lock(an, luna, agent_key, lunar_data, penalty, grad_incasare, note):
    _write(
        "INSERT INTO bonus_istoric "
        "(an, luna, agent_key, lunar_data, penalty_pct, grad_incasare, stare, "
        " inchis_la, note) "
        "VALUES (:an,:luna,:k,:ld,:p,:gi,'inchis',datetime('now','localtime'),:n) "
        "ON CONFLICT(an,luna,agent_key) DO UPDATE SET "
        "  lunar_data=excluded.lunar_data, penalty_pct=excluded.penalty_pct, "
        "  grad_incasare=excluded.grad_incasare, stare='inchis', "
        "  inchis_la=excluded.inchis_la, note=excluded.note",
        {"an": an, "luna": luna, "k": agent_key, "ld": lunar_data,
         "p": penalty, "gi": grad_incasare, "n": note})


def add_agent(agent_key, db_agent, tip_agent="field"):
    _write(
        "INSERT INTO bonus_config (agent_key, db_agent, tip_agent, activ) "
        "VALUES (:k,:d,:t,1) "
        "ON CONFLICT(agent_key) DO UPDATE SET db_agent=excluded.db_agent, "
        "  tip_agent=excluded.tip_agent, activ=1",
        {"k": agent_key, "d": db_agent, "t": tip_agent})


def set_agent_active(agent_key, activ):
    _write("UPDATE bonus_config SET activ=:a WHERE agent_key=:k",
           {"a": int(activ), "k": agent_key})


def field_agents_in_tranzactii():
    """Agenți de teren prezenți în tranzactii dar nu încă în bonus_config."""
    return query("""
        SELECT DISTINCT t.agent FROM tranzactii t
        WHERE t.agent NOT IN ('EMAG','SITE','TRENDYOL','ALTEX')
          AND LOWER(t.agent) NOT IN (
              SELECT LOWER(db_agent) FROM bonus_config WHERE db_agent IS NOT NULL)
        ORDER BY t.agent
    """)
```

- [ ] **Step 4: Re-export în `app/queries/__init__.py`**

Adaugă la blocul `from queries.bonus import (...)`:
```python
    save_obiective as save_obiective,
    istoric_get as istoric_get,
    istoric_lock as istoric_lock,
    add_agent as add_agent,
    set_agent_active as set_agent_active,
    field_agents_in_tranzactii as field_agents_in_tranzactii,
```

- [ ] **Step 5: Rulează → trece**

Run: `python -m pytest tests/test_bonus_queries.py -v`
Expected: toate PASS.

- [ ] **Step 6: Commit**

```bash
git add app/queries/bonus.py app/queries/__init__.py tests/test_bonus_queries.py
git commit -m "feat(bonus): writers obiective + istoric inchidere + management agenti"
```

---

## Phase 3 — Orchestrare blueprint + agregare per lună

### Task 8: Helper de orchestrare `build_agent_month` în blueprint

**Files:**
- Modify: `app/blueprints/bonus.py`
- Test: `tests/test_bonus_routes.py`

Acest helper leagă query-urile de motor: încarcă obiectivele unei luni, completează `actual` (auto sau manual/istoric), aplică grila și întoarce rezultatul gata de render.

- [ ] **Step 1: Scrie testul care pică**

Create `tests/test_bonus_routes.py`:
```python
import sys
import os
import sqlite3
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
import paths


@pytest.fixture
def app_client():
    from app import app  # blueprint-ul bonus e înregistrat în app.py
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def seed_bogdan():
    conn = sqlite3.connect(paths.DB_PATH)
    conn.executemany(
        "INSERT INTO tranzactii (an, luna, data_dl, agent, furnizor, client, "
        "cod_client, val_neta, marja_bruta) VALUES (?,?,?,?,?,?,?,?,?)",
        [(2026, 6, '2026-06-10', 'DRAGNEA BOGDAN', 'Basilur', 'Cl', 'C1', 5000.0, 1500.0)])
    conn.commit(); conn.close()
    yield
    conn = sqlite3.connect(paths.DB_PATH)
    conn.execute("DELETE FROM tranzactii WHERE cod_client='C1'")
    conn.execute("DELETE FROM bonus_lunar_config WHERE agent_key='Bogdan' AND an=2026 AND luna=6")
    conn.execute("DELETE FROM bonus_obiective_strategice WHERE agent_key='Bogdan' AND an=2026 AND luna=6")
    conn.commit(); conn.close()


def test_build_agent_month_auto_actual(seed_bogdan):
    from queries.bonus import save_obiective
    from blueprints.bonus import build_agent_month
    save_obiective(2026, 6, 'Bogdan', 4000.0, 0.20,
                   [{"tip": "vanzari", "referinta": None, "target": 5000.0, "unitate": "ron", "pondere": 1.0}])
    out = build_agent_month('Bogdan', 'DRAGNEA BOGDAN', 2026, 6)
    assert out['kpis'][0]['actual'] == 5000.0     # auto din tranzactii
    assert out['kpis'][0]['realizare'] == 1.0
    assert out['total_bonus'] == 4000.0
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_routes.py::test_build_agent_month_auto_actual -v`
Expected: FAIL (ImportError: `build_agent_month`).

- [ ] **Step 3: Implementează `build_agent_month` în `app/blueprints/bonus.py`**

Adaugă (păstrează importurile existente; adaugă `import json` și importurile noi din `queries`):
```python
def _actual_for_kpi(kpi, db_agent, an, luna, istoric_manual):
    """Completează 'actual' pentru un rând KPI: auto din tranzactii sau manual."""
    tip = kpi["tip"]
    if tip == "vanzari":
        return queries.realizat_auto(db_agent, an, luna)["vanzari"]
    if tip == "marja":
        return queries.realizat_auto(db_agent, an, luna)["marja"]
    if tip == "clienti":
        return queries.realizat_auto(db_agent, an, luna)["clienti"]
    if tip == "brand":
        return queries.realizat_brand(db_agent, kpi["referinta"], an, luna)
    if tip == "clienti_noi_gama":
        return queries.clienti_noi_gama_count(db_agent, kpi["referinta"], an, luna)
    # incasari / scriptic → manual (din istoric înghețat sau realizat_manual)
    return istoric_manual.get(str(kpi.get("id")), kpi.get("realizat_manual") or 0.0)


def build_agent_month(agent_key, db_agent, an, luna):
    """Agregă obiectivele + realizatul + grila → rezultat per agent/lună."""
    cfg = queries.lunar_config(an, luna, agent_key) or {"monthly_bonus": 0, "growth_pct": 0.20}
    rows = queries.obiective(an, luna, agent_key)
    grid = queries.payout_grid(agent_key)
    rec = queries.istoric_get(an, luna, agent_key)

    # Dacă luna e închisă, citește snapshot înghețat
    if rec and rec.get("stare") == "inchis" and rec.get("lunar_data"):
        return json.loads(rec["lunar_data"])

    istoric_manual = {}  # live: manualele neînchise vin din realizat_manual pe rând
    penalty = (rec or {}).get("penalty_pct") or 0.0
    kpis = []
    for r in rows:
        actual = _actual_for_kpi(r, db_agent, an, luna, istoric_manual)
        kpis.append({
            "tip": r["tip"], "referinta": r["referinta"],
            "target": r["target"] or 0.0, "unitate": r["unitate"],
            "pondere": r["pondere"] or 0.0, "actual": actual,
            "id": r["id"],
        })
    out = bonus_calc.calc_agent_month(cfg["monthly_bonus"], penalty, kpis, grid)
    out["agent_key"] = agent_key
    out["monthly_bonus"] = cfg["monthly_bonus"]
    out["an"] = an
    out["luna"] = luna
    out["inchis"] = bool(rec and rec.get("stare") == "inchis")
    return out
```

Asigură-te că fișierul are la început: `import json`, `import queries`, `import bonus_calc` (înlocuiește importurile selective vechi din `bonus_calc` dacă intră în conflict — păstrează `MONTHS_RO`).

- [ ] **Step 4: Rulează → trece**

Run: `python -m pytest tests/test_bonus_routes.py::test_build_agent_month_auto_actual -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/blueprints/bonus.py tests/test_bonus_routes.py
git commit -m "feat(bonus): orchestrare build_agent_month (obiective+realizat+grila)"
```

---

## Phase 4 — Rute și template-uri UI

> Pattern de stil: urmează `app/templates/bonus.html` și `app/templates/agent.html` existente
> (card-uri Bootstrap, `_period_selector.html`, badge-uri culori realizare). Toate paginile
> extind `base.html` și folosesc filtrele Jinja existente (`ron`, `pct`, `delta_class`).

### Task 9: Rebuild tracker `/bonus` (rută + template)

**Files:**
- Modify: `app/blueprints/bonus.py`, `app/templates/bonus.html`
- Test: `tests/test_bonus_routes.py`

- [ ] **Step 1: Scrie testul care pică**

Adaugă în `tests/test_bonus_routes.py`:
```python
def test_bonus_tracker_renders(app_client, seed_bogdan):
    from queries.bonus import save_obiective
    save_obiective(2026, 6, 'Bogdan', 4000.0, 0.20,
                   [{"tip": "vanzari", "referinta": None, "target": 5000.0, "unitate": "ron", "pondere": 1.0}])
    resp = app_client.get('/bonus?an=2026&luna=6')
    assert resp.status_code == 200
    assert b'Bogdan' in resp.data
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_routes.py::test_bonus_tracker_renders -v`
Expected: FAIL (tracker-ul vechi folosește PRESETS / 500 sau lipsă date).

- [ ] **Step 3: Rescrie ruta `bonus()` în `app/blueprints/bonus.py`**

Înlocuiește funcția `bonus()`:
```python
@bonus_bp.route('/bonus')
def bonus():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int) or datetime.date.today().month
    agents = []
    for a in queries.bonus_agents(activ_only=True):
        out = build_agent_month(a['agent_key'], a['db_agent'], an, luna)
        out['db_agent'] = a['db_agent']
        agents.append(out)
    return render_template('bonus.html', agents=agents, an=an, luna=luna,
                           months_ro=BONUS_MONTHS_RO)
```

- [ ] **Step 4: Rescrie `app/templates/bonus.html`**

Înlocuiește conținutul cu un tracker care iterează `agents` și `agent.kpis`:
```html
{% extends 'base.html' %}
{% block title %}Tracker Bonus — Torb Logistic{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0 fw-bold"><i class="bi bi-trophy-fill text-warning me-2"></i>Tracker Bonus Echipă</h4>
  <div class="d-flex gap-2">
    <a href="{{ url_for('bonus.obiective') }}?an={{ an }}&luna={{ luna }}" class="btn btn-sm btn-primary">
      <i class="bi bi-bullseye me-1"></i> Setare Obiective</a>
    <a href="{{ url_for('bonus.inchidere') }}?an={{ an }}&luna={{ luna }}" class="btn btn-sm btn-outline-dark">
      <i class="bi bi-lock-fill me-1"></i> Închidere Lună</a>
    <a href="{{ url_for('bonus.bonus_export') }}" class="btn btn-sm btn-success">
      <i class="bi bi-file-earmark-excel me-1"></i> Export</a>
  </div>
</div>
{% include '_period_selector.html' %}

<div class="row row-cols-1 row-cols-xl-2 g-3">
  {% for a in agents %}
  <div class="col">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-header bg-white d-flex justify-content-between align-items-center">
        <span class="fw-bold">{{ a.agent_key }}
          {% if a.inchis %}<span class="badge bg-dark ms-1">închis</span>{% endif %}
        </span>
        <span class="fw-bold {{ 'text-success' if a.total_bonus > 0 else 'text-muted' }}">
          {{ a.total_bonus | int }} / {{ a.monthly_bonus | int }} RON</span>
      </div>
      <div class="table-responsive">
        <table class="table table-sm mb-0" style="font-size:.8rem">
          <thead class="table-light">
            <tr><th>KPI</th><th>Referință</th><th class="text-end">Target</th>
                <th class="text-end">Realizat</th><th class="text-center">%</th>
                <th class="text-end">Pond.</th><th class="text-end">Bonus</th><th></th></tr>
          </thead>
          <tbody>
            {% for k in a.kpis %}
            {% set rp = (k.realizare * 100) %}
            <tr>
              <td>{{ k.tip }}</td>
              <td class="small">{{ k.referinta or '—' }}</td>
              <td class="text-end">{{ k.target | int }}</td>
              <td class="text-end">{{ k.actual | int }}</td>
              <td class="text-center fw-semibold
                {% if rp >= 100 %}text-success{% elif rp >= 80 %}text-warning{% else %}text-danger{% endif %}">
                {{ rp | round(0) | int }}%</td>
              <td class="text-end small text-muted">{{ (k.pondere * 100) | round(0) | int }}%</td>
              <td class="text-end {{ 'text-success' if k.bonus > 0 else 'text-muted' }}">
                {{ k.bonus | int if k.bonus > 0 else '—' }}</td>
              <td>
                {% if k.tip == 'clienti_noi_gama' %}
                <a class="small" href="{{ url_for('bonus.clienti_noi_gama') }}?agent={{ a.db_agent }}&gama={{ k.referinta }}&an={{ an }}&luna={{ luna }}">
                  <i class="bi bi-people"></i></a>
                {% endif %}
              </td>
            </tr>
            {% else %}
            <tr><td colspan="8" class="text-center text-muted py-3">
              Niciun obiectiv setat. <a href="{{ url_for('bonus.obiective') }}?an={{ an }}&luna={{ luna }}">Setează acum</a></td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 5: Rulează → trece**

Run: `python -m pytest tests/test_bonus_routes.py::test_bonus_tracker_renders -v`
Expected: PASS.

- [ ] **Step 6: Smoke manual**

Run: `python -m pytest tests/test_flask_routes.py -v` (verifică să nu fi spart rute existente). Apoi pornește app-ul și deschide `/bonus?an=2026&luna=6` vizual.
Expected: pagina se încarcă, agenții apar.

- [ ] **Step 7: Commit**

```bash
git add app/blueprints/bonus.py app/templates/bonus.html tests/test_bonus_routes.py
git commit -m "feat(bonus): rebuild tracker /bonus din DB config-driven"
```

### Task 10: Pagina de setare obiective `/bonus/obiective` (varianta C) + save

**Files:**
- Modify: `app/blueprints/bonus.py`
- Create: `app/templates/bonus/obiective.html`
- Test: `tests/test_bonus_routes.py`

- [ ] **Step 1: Scrie testele care pică**

Adaugă în `tests/test_bonus_routes.py`:
```python
def test_obiective_page_renders(app_client):
    resp = app_client.get('/bonus/obiective?an=2026&luna=7')
    assert resp.status_code == 200
    assert b'Bogdan' in resp.data

def test_obiective_save_roundtrip(app_client):
    payload = {
        "an": 2026, "luna": 9, "agent_key": "Ionut",
        "monthly_bonus": 2000, "growth_pct": 0.20,
        "kpis": [{"tip": "vanzari", "referinta": None, "target": 50000,
                  "unitate": "ron", "pondere": 1.0}],
    }
    resp = app_client.post('/bonus/obiective/save', json=payload)
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    from queries.bonus import obiective
    assert len(obiective(2026, 9, 'Ionut')) == 1
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_routes.py::test_obiective_page_renders -v`
Expected: FAIL (rută inexistentă → 404).

- [ ] **Step 3: Adaugă rutele în `app/blueprints/bonus.py`**

```python
# Cele 5 game pre-încărcate implicit la creare obiective noi
DEFAULT_GAME = [
    ("Basilur", 0.30), ("Toras", 0.25), ("Leonex", 0.20),
    ("Celmar", 0.15), ("Delaviuda", 0.10),
]
ALL_GAME = ['Basilur', 'Toras', 'Celmar', 'Leonex', 'Delaviuda',
            'KingsLeaf', 'Solvex', 'Tipson', 'Cosmetice']


def _proposed_kpis(db_agent, an, luna, growth=0.20):
    """Propune rândurile implicite cu target = PY same-month * (1+growth)."""
    py = queries.py_baseline(db_agent, an, luna)
    g = 1.0 + growth
    kpis = [
        {"tip": "vanzari", "referinta": None, "py": py["vanzari"],
         "target": round(py["vanzari"] * g), "unitate": "ron", "pondere": 0.0},
        {"tip": "marja", "referinta": None, "py": py["marja"],
         "target": round(py["marja"] * g), "unitate": "ron", "pondere": 0.0},
    ]
    for gama, pond in DEFAULT_GAME:
        base = py["brand"].get(gama, 0)
        kpis.append({"tip": "brand", "referinta": gama, "py": base,
                     "target": round(base * g), "unitate": "ron", "pondere": pond})
    return kpis


@bonus_bp.route('/bonus/obiective')
def obiective():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int) or datetime.date.today().month
    agents = []
    for a in queries.bonus_agents(activ_only=True):
        existing = queries.obiective(an, luna, a['agent_key'])
        cfg = queries.lunar_config(an, luna, a['agent_key'])
        total_pond = sum((r['pondere'] or 0) for r in existing)
        agents.append({
            "agent_key": a['agent_key'], "db_agent": a['db_agent'],
            "has_obiective": bool(existing), "n_kpi": len(existing),
            "monthly_bonus": (cfg or {}).get('monthly_bonus'),
            "total_pondere": round(total_pond * 100),
            "kpis": existing or _proposed_kpis(a['db_agent'], an, luna),
        })
    return render_template('bonus/obiective.html', agents=agents, an=an, luna=luna,
                           all_game=ALL_GAME, months_ro=BONUS_MONTHS_RO)


@bonus_bp.route('/bonus/obiective/save', methods=['POST'])
def obiective_save():
    d = request.get_json(silent=True) or {}
    try:
        queries.save_obiective(
            int(d['an']), int(d['luna']), d['agent_key'],
            float(d['monthly_bonus']), float(d.get('growth_pct', 0.20)),
            d.get('kpis', []))
        return jsonify({'ok': True})
    except Exception as exc:
        logger.exception("obiective_save failed")
        return jsonify({'ok': False, 'error': str(exc)}), 400
```

- [ ] **Step 4: Creează `app/templates/bonus/obiective.html`**

Implementează varianta C: card-uri stare + formular per agent. Structură (urmează mockup-ul aprobat):
```html
{% extends 'base.html' %}
{% block title %}Setare Obiective — Torb Logistic{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0 fw-bold"><i class="bi bi-bullseye text-primary me-2"></i>Setare Obiective Lunare</h4>
  <a href="{{ url_for('bonus.bonus') }}?an={{ an }}&luna={{ luna }}" class="btn btn-sm btn-outline-secondary">
    <i class="bi bi-arrow-left"></i> Tracker</a>
</div>
{% include '_period_selector.html' %}

<!-- Card-uri stare agenți -->
<div class="d-flex gap-2 flex-wrap mb-3">
  {% for a in agents %}
  <div class="card border {{ 'border-primary' if loop.first else '' }}" style="cursor:pointer;min-width:150px"
       onclick="selectAgent('{{ a.agent_key }}')" id="card-{{ a.agent_key }}">
    <div class="card-body p-2">
      <div class="fw-bold">{{ a.agent_key }}</div>
      {% if a.has_obiective %}
        <div class="small {{ 'text-success' if a.total_pondere == 100 else 'text-danger' }}">
          ✓ {{ a.n_kpi }} KPI · {{ a.total_pondere }}%</div>
      {% else %}
        <div class="small text-warning">⚠ lipsă obiective</div>
      {% endif %}
    </div>
  </div>
  {% endfor %}
</div>

<!-- Formular per agent (un panou per agent, ascuns/afișat din JS) -->
{% for a in agents %}
<div class="card border-0 shadow-sm agent-form" id="form-{{ a.agent_key }}"
     style="{{ '' if loop.first else 'display:none' }}">
  <div class="card-body">
    <div class="d-flex align-items-center gap-2 mb-3">
      <strong>{{ a.agent_key }} — {{ months_ro[luna-1] }} {{ an }}</strong>
      <span class="text-muted ms-2">Bonus lunar:</span>
      <input type="number" class="form-control form-control-sm" style="width:90px"
             id="mb-{{ a.agent_key }}" value="{{ a.monthly_bonus or 0 }}">
      <span class="text-muted ms-2">Creștere %:</span>
      <input type="number" class="form-control form-control-sm" style="width:70px"
             id="g-{{ a.agent_key }}" value="20">
    </div>
    <table class="table table-sm align-middle" id="tbl-{{ a.agent_key }}">
      <thead class="table-light"><tr>
        <th>Criteriu</th><th>Referință</th><th class="text-end">PY</th>
        <th class="text-end">Target</th><th class="text-end">Pondere %</th><th></th>
      </tr></thead>
      <tbody>
        {% for k in a.kpis %}
        <tr data-tip="{{ k.tip }}">
          <td>{{ k.tip }}</td>
          <td>
            {% if k.tip in ('brand','clienti_noi_gama') %}
              <select class="form-select form-select-sm ref">
                {% for g in all_game %}<option {{ 'selected' if g == k.referinta else '' }}>{{ g }}</option>{% endfor %}
              </select>
            {% elif k.tip == 'scriptic' %}
              <input class="form-control form-control-sm ref" value="{{ k.referinta or '' }}">
            {% else %}—{% endif %}
          </td>
          <td class="text-end text-muted small">{{ k.py | int if k.py is defined and k.py else '—' }}</td>
          <td class="text-end"><input type="number" class="form-control form-control-sm target text-end" value="{{ k.target | int }}"></td>
          <td class="text-end"><input type="number" class="form-control form-control-sm pond text-end" style="width:70px" value="{{ (k.pondere * 100) | round(0) | int }}"></td>
          <td><button class="btn btn-sm btn-outline-danger" onclick="this.closest('tr').remove();recalcPond('{{ a.agent_key }}')">×</button></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <div class="d-flex gap-2 align-items-center">
      <button class="btn btn-sm btn-outline-primary" onclick="addRow('{{ a.agent_key }}','brand')">+ Gamă</button>
      <button class="btn btn-sm btn-outline-primary" onclick="addRow('{{ a.agent_key }}','clienti_noi_gama')">+ Clienți noi/gamă</button>
      <button class="btn btn-sm btn-outline-primary" onclick="addRow('{{ a.agent_key }}','clienti')">+ Nr clienți</button>
      <button class="btn btn-sm btn-outline-primary" onclick="addRow('{{ a.agent_key }}','incasari')">+ Încasări</button>
      <button class="btn btn-sm btn-outline-primary" onclick="addRow('{{ a.agent_key }}','scriptic')">+ Scriptic</button>
      <span class="ms-auto fw-bold" id="pondtot-{{ a.agent_key }}"></span>
      <button class="btn btn-sm btn-success" onclick="saveAgent('{{ a.agent_key }}')">💾 Salvează</button>
    </div>
  </div>
</div>
{% endfor %}
{% endblock %}

{% block scripts %}
<script>
const AN = {{ an }}, LUNA = {{ luna }};
const ALL_GAME = {{ all_game | tojson }};
function selectAgent(k){
  document.querySelectorAll('.agent-form').forEach(f=>f.style.display='none');
  document.getElementById('form-'+k).style.display='';
  document.querySelectorAll('[id^=card-]').forEach(c=>c.classList.remove('border-primary'));
  document.getElementById('card-'+k).classList.add('border-primary');
}
function recalcPond(k){
  let t=0; document.querySelectorAll('#tbl-'+k+' .pond').forEach(i=>t+=parseFloat(i.value||0));
  const el=document.getElementById('pondtot-'+k);
  el.textContent='Total pondere: '+t+'%';
  el.className='ms-auto fw-bold '+(t==100?'text-success':'text-danger');
}
function addRow(k,tip){
  const tb=document.querySelector('#tbl-'+k+' tbody');
  const refCell = (tip==='brand'||tip==='clienti_noi_gama')
    ? '<select class="form-select form-select-sm ref">'+ALL_GAME.map(g=>'<option>'+g+'</option>').join('')+'</select>'
    : (tip==='scriptic' ? '<input class="form-control form-control-sm ref">' : '—');
  const tr=document.createElement('tr'); tr.dataset.tip=tip;
  tr.innerHTML='<td>'+tip+'</td><td>'+refCell+'</td><td class="text-end text-muted">—</td>'+
    '<td class="text-end"><input type="number" class="form-control form-control-sm target text-end" value="0"></td>'+
    '<td class="text-end"><input type="number" class="form-control form-control-sm pond text-end" style="width:70px" value="0"></td>'+
    '<td><button class="btn btn-sm btn-outline-danger" onclick="this.closest(\'tr\').remove();recalcPond(\''+k+'\')">×</button></td>';
  tb.appendChild(tr);
  tr.querySelector('.pond').addEventListener('input',()=>recalcPond(k));
  recalcPond(k);
}
function saveAgent(k){
  const kpis=[...document.querySelectorAll('#tbl-'+k+' tbody tr')].map(tr=>({
    tip:tr.dataset.tip,
    referinta: tr.querySelector('.ref') ? (tr.querySelector('.ref').value||null) : null,
    target: parseFloat(tr.querySelector('.target').value||0),
    unitate: tr.dataset.tip==='scriptic' ? 'pct' : (tr.dataset.tip==='clienti'||tr.dataset.tip==='clienti_noi_gama' ? 'nr':'ron'),
    pondere: parseFloat(tr.querySelector('.pond').value||0)/100,
  }));
  fetch('{{ url_for("bonus.obiective_save") }}',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({an:AN,luna:LUNA,agent_key:k,
      monthly_bonus:parseFloat(document.getElementById('mb-'+k).value||0),
      growth_pct:parseFloat(document.getElementById('g-'+k).value||20)/100,kpis})})
   .then(r=>r.json()).then(d=>{ if(d.ok){location.reload();} else {alert('Eroare: '+d.error);} });
}
document.querySelectorAll('[id^=tbl-] .pond').forEach(i=>i.addEventListener('input',e=>recalcPond(e.target.closest('table').id.replace('tbl-',''))));
{% for a in agents %}recalcPond('{{ a.agent_key }}');{% endfor %}
</script>
{% endblock %}
```

- [ ] **Step 5: Rulează → trece**

Run: `python -m pytest tests/test_bonus_routes.py -v`
Expected: `test_obiective_page_renders` și `test_obiective_save_roundtrip` PASS.

- [ ] **Step 6: Commit**

```bash
git add app/blueprints/bonus.py app/templates/bonus/obiective.html tests/test_bonus_routes.py
git commit -m "feat(bonus): pagina setare obiective (varianta C) + save"
```

### Task 11: Drill-down `/bonus/clienti-noi-gama`

**Files:**
- Modify: `app/blueprints/bonus.py`
- Create: `app/templates/bonus/clienti_noi_gama.html`
- Test: `tests/test_bonus_routes.py`

- [ ] **Step 1: Scrie testul care pică**

Adaugă în `tests/test_bonus_routes.py`:
```python
def test_clienti_noi_gama_page(app_client, seed_bogdan):
    resp = app_client.get('/bonus/clienti-noi-gama?agent=DRAGNEA BOGDAN&gama=Basilur&an=2026&luna=6')
    assert resp.status_code == 200
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_routes.py::test_clienti_noi_gama_page -v`
Expected: FAIL (404).

- [ ] **Step 3: Adaugă ruta în `app/blueprints/bonus.py`**

```python
@bonus_bp.route('/bonus/clienti-noi-gama')
def clienti_noi_gama():
    agent = request.args.get('agent', '')
    gama  = request.args.get('gama', '')
    an    = int(request.args.get('an', datetime.date.today().year))
    luna  = int(request.args.get('luna', datetime.date.today().month))
    rows = queries.clienti_noi_gama_list(agent, gama, an, luna)
    return render_template('bonus/clienti_noi_gama.html',
                           rows=rows, agent=agent, gama=gama, an=an, luna=luna,
                           months_ro=BONUS_MONTHS_RO)
```

- [ ] **Step 4: Creează `app/templates/bonus/clienti_noi_gama.html`**

```html
{% extends 'base.html' %}
{% block title %}Clienți noi {{ gama }} — Torb Logistic{% endblock %}
{% block content %}
<nav class="mb-3"><a href="{{ url_for('bonus.bonus') }}?an={{ an }}&luna={{ luna }}" class="text-decoration-none">
  <i class="bi bi-arrow-left"></i> Tracker Bonus</a></nav>
<h4 class="fw-bold mb-3">
  <i class="bi bi-people-fill text-primary me-2"></i>
  Clienți noi pe gama <strong>{{ gama }}</strong> — {{ agent }} · {{ months_ro[luna-1] }} {{ an }}
</h4>
<p class="text-muted">Clienți facturați cu gama {{ gama }} în {{ months_ro[luna-1] }} {{ an }},
  care nu au mai fost facturați cu această gamă în ultimele 24 de luni.</p>
<div class="card shadow-sm border-0">
  <div class="table-responsive">
    <table class="table table-hover mb-0">
      <thead class="table-dark"><tr><th>#</th><th>Cod client</th><th>Client</th></tr></thead>
      <tbody>
        {% for r in rows %}
        <tr><td>{{ loop.index }}</td><td>{{ r.cod_client }}</td>
          <td><a href="{{ url_for('analytics.client_detail', cod_client=r.cod_client, an=an) }}"
                 class="text-decoration-none">{{ r.client }}</a></td></tr>
        {% else %}
        <tr><td colspan="3" class="text-center text-muted py-4">Niciun client nou pe această gamă.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Rulează → trece**

Run: `python -m pytest tests/test_bonus_routes.py::test_clienti_noi_gama_page -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/blueprints/bonus.py app/templates/bonus/clienti_noi_gama.html tests/test_bonus_routes.py
git commit -m "feat(bonus): drill-down clienti noi pe gama"
```

### Task 12: Închidere lună `/bonus/inchidere` + lock

**Files:**
- Modify: `app/blueprints/bonus.py`
- Create: `app/templates/bonus/inchidere.html`
- Test: `tests/test_bonus_routes.py`

- [ ] **Step 1: Scrie testele care pică**

Adaugă în `tests/test_bonus_routes.py`:
```python
def test_inchidere_page_renders(app_client):
    resp = app_client.get('/bonus/inchidere?an=2026&luna=6')
    assert resp.status_code == 200

def test_inchidere_lock_freezes(app_client, seed_bogdan):
    from queries.bonus import save_obiective, istoric_get
    save_obiective(2026, 6, 'Bogdan', 4000.0, 0.20,
                   [{"tip": "incasari", "referinta": None, "target": 1000.0, "unitate": "ron", "pondere": 1.0}])
    payload = {"an": 2026, "luna": 6, "agent_key": "Bogdan", "penalty": 0.0,
               "grad_incasare": 1.0, "note": "ok",
               "manual": {"incasari": 1000.0}}
    resp = app_client.post('/bonus/inchidere/lock', json=payload)
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    rec = istoric_get(2026, 6, 'Bogdan')
    assert rec['stare'] == 'inchis'
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_routes.py::test_inchidere_page_renders -v`
Expected: FAIL (404).

- [ ] **Step 3: Adaugă rutele în `app/blueprints/bonus.py`**

```python
@bonus_bp.route('/bonus/inchidere')
def inchidere():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int) or datetime.date.today().month
    agents = []
    for a in queries.bonus_agents(activ_only=True):
        out = build_agent_month(a['agent_key'], a['db_agent'], an, luna)
        # rândurile manuale care au nevoie de introducere
        manual = [k for k in out['kpis'] if k['tip'] in ('incasari', 'scriptic')]
        rec = queries.istoric_get(an, luna, a['agent_key'])
        agents.append({**out, 'db_agent': a['db_agent'],
                       'manual': manual, 'stare': (rec or {}).get('stare', 'deschis')})
    return render_template('bonus/inchidere.html', agents=agents, an=an, luna=luna,
                           months_ro=BONUS_MONTHS_RO)


@bonus_bp.route('/bonus/inchidere/lock', methods=['POST'])
def inchidere_lock():
    import json as _json
    d = request.get_json(silent=True) or {}
    try:
        an = int(d['an']); luna = int(d['luna']); key = d['agent_key']
        agent_cfg = next((a for a in queries.bonus_agents(activ_only=False)
                          if a['agent_key'] == key), None)
        db_agent = agent_cfg['db_agent'] if agent_cfg else key
        out = build_agent_month(key, db_agent, an, luna)
        # suprascrie actualele manuale cu valorile introduse + recalculează
        manual = d.get('manual', {})
        grid = queries.payout_grid(key)
        for k in out['kpis']:
            if k['tip'] in ('incasari', 'scriptic'):
                k['actual'] = float(manual.get(k['tip'], k.get('actual') or 0))
        recalced = bonus_calc.calc_agent_month(
            out['monthly_bonus'], float(d.get('penalty', 0.0)), out['kpis'], grid)
        recalced.update({'agent_key': key, 'monthly_bonus': out['monthly_bonus'],
                         'an': an, 'luna': luna, 'inchis': True})
        queries.istoric_lock(an, luna, key, _json.dumps(recalced),
                             float(d.get('penalty', 0.0)),
                             float(d.get('grad_incasare', 1.0)), d.get('note', ''))
        return jsonify({'ok': True})
    except Exception as exc:
        logger.exception("inchidere_lock failed")
        return jsonify({'ok': False, 'error': str(exc)}), 400
```

- [ ] **Step 4: Creează `app/templates/bonus/inchidere.html`**

```html
{% extends 'base.html' %}
{% block title %}Închidere Lună — Torb Logistic{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0 fw-bold"><i class="bi bi-lock-fill text-dark me-2"></i>Închidere Lună</h4>
  <a href="{{ url_for('bonus.bonus') }}?an={{ an }}&luna={{ luna }}" class="btn btn-sm btn-outline-secondary">
    <i class="bi bi-arrow-left"></i> Tracker</a>
</div>
{% include '_period_selector.html' %}

{% for a in agents %}
<div class="card border-0 shadow-sm mb-3">
  <div class="card-header bg-white d-flex justify-content-between">
    <span class="fw-bold">{{ a.agent_key }}
      {% if a.stare == 'inchis' %}<span class="badge bg-dark ms-1">închis</span>{% endif %}</span>
    <span class="text-muted">Bonus provizoriu: <strong>{{ a.total_bonus | int }}</strong> RON</span>
  </div>
  <div class="card-body">
    {% if a.manual %}
    <p class="small text-muted mb-2">Introdu realizatul manual pentru criteriile fără date automate:</p>
    {% for k in a.manual %}
    <div class="row g-2 align-items-center mb-2">
      <div class="col-auto"><span class="badge bg-warning text-dark">{{ k.tip }}</span> {{ k.referinta or '' }}</div>
      <div class="col-auto text-muted small">target {{ k.target | int }}{{ '%' if k.tip == 'scriptic' else ' RON' }}</div>
      <div class="col-auto">
        <input type="number" class="form-control form-control-sm manual-input"
               data-agent="{{ a.agent_key }}" data-tip="{{ k.tip }}" style="width:120px"
               placeholder="realizat" {{ 'disabled' if a.stare == 'inchis' else '' }}>
      </div>
    </div>
    {% endfor %}
    {% else %}
    <p class="small text-muted mb-2">Toate criteriile sunt automate. Confirmă închiderea.</p>
    {% endif %}
    <div class="row g-2 align-items-center mt-2">
      <div class="col-auto text-muted small">Penalizare %:</div>
      <div class="col-auto"><input type="number" class="form-control form-control-sm" id="pen-{{ a.agent_key }}" value="0" style="width:80px" {{ 'disabled' if a.stare == 'inchis' else '' }}></div>
      <div class="col-auto text-muted small">Notă:</div>
      <div class="col"><input class="form-control form-control-sm" id="note-{{ a.agent_key }}" {{ 'disabled' if a.stare == 'inchis' else '' }}></div>
      <div class="col-auto">
        <button class="btn btn-sm btn-dark" onclick="lockAgent('{{ a.agent_key }}')"
                {{ 'disabled' if a.stare == 'inchis' else '' }}>
          <i class="bi bi-lock-fill me-1"></i>Închide & îngheață</button>
      </div>
    </div>
  </div>
</div>
{% endfor %}
{% endblock %}

{% block scripts %}
<script>
const AN={{ an }}, LUNA={{ luna }};
function lockAgent(k){
  const manual={};
  document.querySelectorAll('.manual-input[data-agent="'+k+'"]').forEach(i=>{
    manual[i.dataset.tip]=parseFloat(i.value||0);
  });
  fetch('{{ url_for("bonus.inchidere_lock") }}',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({an:AN,luna:LUNA,agent_key:k,
      penalty:parseFloat(document.getElementById('pen-'+k).value||0)/100,
      grad_incasare:1.0,note:document.getElementById('note-'+k).value,manual})})
   .then(r=>r.json()).then(d=>{ if(d.ok){location.reload();} else {alert('Eroare: '+d.error);} });
}
</script>
{% endblock %}
```

- [ ] **Step 5: Rulează → trece**

Run: `python -m pytest tests/test_bonus_routes.py -v`
Expected: `test_inchidere_page_renders` și `test_inchidere_lock_freezes` PASS.

- [ ] **Step 6: Commit**

```bash
git add app/blueprints/bonus.py app/templates/bonus/inchidere.html tests/test_bonus_routes.py
git commit -m "feat(bonus): inchidere luna cu introducere manuala + lock istoric"
```

### Task 13: Management agenți `/bonus/config`

**Files:**
- Modify: `app/blueprints/bonus.py`
- Create: `app/templates/bonus/config.html`
- Test: `tests/test_bonus_routes.py`

- [ ] **Step 1: Scrie testele care pică**

Adaugă în `tests/test_bonus_routes.py`:
```python
def test_config_page_renders(app_client):
    resp = app_client.get('/bonus/config')
    assert resp.status_code == 200
    assert b'Bogdan' in resp.data

def test_config_add_agent(app_client):
    resp = app_client.post('/bonus/config/agent',
                           json={"agent_key": "TestX", "db_agent": "TEST X", "tip_agent": "field"})
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    from queries.bonus import bonus_agents
    assert 'TestX' in {a['agent_key'] for a in bonus_agents(activ_only=False)}
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_routes.py::test_config_page_renders -v`
Expected: FAIL (404).

- [ ] **Step 3: Adaugă rutele în `app/blueprints/bonus.py`**

```python
@bonus_bp.route('/bonus/config')
def config():
    agents = queries.bonus_agents(activ_only=False)
    candidati = queries.field_agents_in_tranzactii()
    return render_template('bonus/config.html', agents=agents, candidati=candidati)


@bonus_bp.route('/bonus/config/agent', methods=['POST'])
def config_add_agent():
    d = request.get_json(silent=True) or {}
    try:
        queries.add_agent(d['agent_key'], d.get('db_agent'), d.get('tip_agent', 'field'))
        return jsonify({'ok': True})
    except Exception as exc:
        logger.exception("config_add_agent failed")
        return jsonify({'ok': False, 'error': str(exc)}), 400


@bonus_bp.route('/bonus/config/agent/<agent_key>/active', methods=['POST'])
def config_set_active(agent_key):
    d = request.get_json(silent=True) or {}
    queries.set_agent_active(agent_key, int(d.get('activ', 1)))
    return jsonify({'ok': True})
```

- [ ] **Step 4: Creează `app/templates/bonus/config.html`**

```html
{% extends 'base.html' %}
{% block title %}Configurare Agenți Bonus — Torb Logistic{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0 fw-bold"><i class="bi bi-gear-fill text-secondary me-2"></i>Configurare Agenți Bonus</h4>
  <a href="{{ url_for('bonus.bonus') }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-arrow-left"></i> Tracker</a>
</div>

<div class="card shadow-sm border-0 mb-3">
  <div class="card-header bg-white fw-semibold">Agenți configurați</div>
  <div class="table-responsive">
    <table class="table mb-0">
      <thead class="table-light"><tr><th>Cheie</th><th>Agent DB</th><th>Tip</th><th>Activ</th></tr></thead>
      <tbody>
        {% for a in agents %}
        <tr>
          <td class="fw-semibold">{{ a.agent_key }}</td>
          <td class="small text-muted">{{ a.db_agent }}</td>
          <td>{{ a.tip_agent }}</td>
          <td>
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" {{ 'checked' if a.activ else '' }}
                     onchange="setActive('{{ a.agent_key }}', this.checked)">
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

{% if candidati %}
<div class="card shadow-sm border-0">
  <div class="card-header bg-white fw-semibold">Agenți noi în baza de date (neconfigurați)</div>
  <ul class="list-group list-group-flush">
    {% for c in candidati %}
    <li class="list-group-item d-flex justify-content-between align-items-center">
      <span>{{ c.agent }}</span>
      <button class="btn btn-sm btn-outline-primary"
              onclick="addAgent('{{ c.agent }}')">+ Adaugă la bonus</button>
    </li>
    {% endfor %}
  </ul>
</div>
{% endif %}
{% endblock %}

{% block scripts %}
<script>
function setActive(k, on){
  fetch('/bonus/config/agent/'+encodeURIComponent(k)+'/active',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({activ:on?1:0})});
}
function addAgent(dbAgent){
  const key = prompt('Cheie scurtă pentru agent (ex. prenume):', dbAgent.split(' ')[0]);
  if(!key) return;
  fetch('{{ url_for("bonus.config_add_agent") }}',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({agent_key:key,db_agent:dbAgent,tip_agent:'field'})})
   .then(r=>r.json()).then(d=>{ if(d.ok) location.reload(); else alert('Eroare: '+d.error); });
}
</script>
{% endblock %}
```

- [ ] **Step 5: Adaugă link în meniu**

În `app/templates/bonus.html`, în bara de butoane sus, adaugă lângă "Setare Obiective":
```html
    <a href="{{ url_for('bonus.config') }}" class="btn btn-sm btn-outline-secondary">
      <i class="bi bi-gear"></i> Agenți</a>
```

- [ ] **Step 6: Rulează → trece**

Run: `python -m pytest tests/test_bonus_routes.py -v`
Expected: toate PASS.

- [ ] **Step 7: Commit**

```bash
git add app/blueprints/bonus.py app/templates/bonus/config.html app/templates/bonus.html tests/test_bonus_routes.py
git commit -m "feat(bonus): management agenti (adauga din DB / activeaza)"
```

---

## Phase 5 — Adaptare export + curățare cod mort

### Task 14: Adaptează exportul Excel la noul model

**Files:**
- Modify: `app/blueprints/bonus.py`
- Test: `tests/test_bonus_routes.py`

- [ ] **Step 1: Scrie testul care pică**

Adaugă în `tests/test_bonus_routes.py`:
```python
def test_bonus_export_ok(app_client):
    resp = app_client.get('/bonus/export?an=2026&luna=6')
    assert resp.status_code == 200
    assert 'spreadsheet' in resp.headers.get('Content-Type', '')
```

- [ ] **Step 2: Rulează → pică**

Run: `python -m pytest tests/test_bonus_routes.py::test_bonus_export_ok -v`
Expected: FAIL (exportul vechi folosește PRESETS → eroare sau coloane vechi).

- [ ] **Step 3: Rescrie `bonus_export()` în `app/blueprints/bonus.py`**

```python
@bonus_bp.route('/bonus/export')
def bonus_export():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int) or datetime.date.today().month
    summary, sheets = [], {}
    for a in queries.bonus_agents(activ_only=True):
        out = build_agent_month(a['agent_key'], a['db_agent'], an, luna)
        summary.append({
            'Agent': a['agent_key'], 'Bonus Lunar': out['monthly_bonus'],
            'Scor': round(out['scor'], 2), 'Bonus Realizat': round(out['total_bonus']),
            'Închis': 'Da' if out.get('inchis') else 'Nu',
        })
        sheets[a['agent_key'][:31]] = [{
            'KPI': k['tip'], 'Referință': k['referinta'] or '',
            'Target': k['target'], 'Realizat': k['actual'],
            'Realizare %': round(k['realizare'] * 100, 1),
            'Pondere %': round(k['pondere'] * 100),
            'Multiplicator': k['multiplier'], 'Bonus': round(k['bonus']),
        } for k in out['kpis']]
    sheets = {'Centralizare': summary, **sheets}
    return send_excel(sheets, timestamped_filename('bonus_echipa'))
```

- [ ] **Step 4: Rulează → trece**

Run: `python -m pytest tests/test_bonus_routes.py::test_bonus_export_ok -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/blueprints/bonus.py tests/test_bonus_routes.py
git commit -m "feat(bonus): export Excel adaptat la modelul KPI generic"
```

### Task 15: Retragere `PRESETS` și cod mort din `bonus_calc.py` + simulator

**Files:**
- Modify: `app/blueprints/bonus.py`, `app/bonus_calc.py`
- Test: rulează toată suita

> Scope: `simulate`, `calc_month`, `PRESETS`, `STRATEGIC_WEIGHTS_DEFAULT`, `_build_agent_months_data`,
> rutele `bonus_simulator`, `api_bonus_agent_data`, `api_bonus_simulate`, `bonus_simulator_export`
> nu mai sunt folosite de noul tracker. Le ELIMINĂM pentru a evita confuzia (YAGNI), DUPĂ ce noul
> flux e verde.

- [ ] **Step 1: Identifică referințele**

Run: `grep -rn "PRESETS\|_build_agent_months_data\|bonus_simulator\|api_bonus\|simulate\|calc_month" app/ --include=*.py | grep -v __pycache__`
Expected: doar `app/blueprints/bonus.py`, `app/bonus_calc.py`, `tests/test_bonus_calc.py`.

- [ ] **Step 2: Elimină rutele simulator din `app/blueprints/bonus.py`**

Șterge funcțiile: `bonus_simulator`, `api_bonus_agent_data`, `api_bonus_simulate`,
`bonus_simulator_export`, `_build_agent_months_data`. Șterge importurile devenite nefolosite din
`bonus_calc` (`PRESETS`, `SIM_MONTHS`, `STRATEGIC_BRANDS`, `STRATEGIC_WEIGHTS_DEFAULT`, `simulate`).
Păstrează `MONTHS_RO as BONUS_MONTHS_RO`.

Verifică în `app/templates/bonus.html` că nu mai există link `bonus.bonus_simulator`; dacă există,
elimină-l (a fost deja înlocuit în Task 9).

- [ ] **Step 3: Elimină `PRESETS`, `simulate`, `calc_month`, `STRATEGIC_*` din `app/bonus_calc.py`**

Păstrează: `PAYOUT_GRID`, `MONTHS_RO`, `SIM_MONTHS` (dacă mai e folosit — altfel șterge),
`payout_multiplier`, `calc_kpi`, `calc_agent_month`. Șterge testele vechi din
`tests/test_bonus_calc.py` care testează `calc_month`/`simulate` (funcțiile dispar).

- [ ] **Step 4: Șterge template-ul `app/templates/bonus_simulator.html`**

Run: `git rm app/templates/bonus_simulator.html`

- [ ] **Step 5: Rulează toată suita + ruff**

Run: `python -m pytest tests/ -q && ruff check .`
Expected: toate testele PASS, ruff zero erori.

- [ ] **Step 6: Smoke manual complet**

Pornește app-ul (`Start-Hub.bat` sau `python app/app.py`). Verifică fluxul:
`/bonus` → `/bonus/obiective` (setează un agent, salvează) → `/bonus` (apare) →
`/bonus/inchidere` (închide) → `/bonus` (badge "închis") → `/bonus/config` (adaugă/dezactivează) →
drill-down clienți noi.
Expected: fără erori în consolă; valorile persistă.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(bonus): elimina PRESETS/simulator (cod mort) dupa migrare config-driven"
```

---

## Phase 6 — Regresie & verificare finală

### Task 16: Test de regresie pe o lună cunoscută + verificare finală

**Files:**
- Test: `tests/test_bonus_routes.py`

- [ ] **Step 1: Verifică paritatea cu seed-ul 2025 existent**

`bonus_lunar_config` are seed pt. 2025 (monthly_bonus per agent). Verifică pe DB-ul viu că tracker-ul
nu dă eroare pe o lună 2025 și că un agent cu obiective seed-uite afișează bonus calculat.

Run: `python -c "import sys; sys.path.insert(0,'app'); from app import app; c=app.test_client(); r=c.get('/bonus?an=2025&luna=6'); print(r.status_code)"`
Expected: `200`.

- [ ] **Step 2: Rulează întreaga suită**

Run: `python -m pytest tests/ -v`
Expected: toate PASS.

- [ ] **Step 3: Ruff final**

Run: `ruff check .`
Expected: zero erori.

- [ ] **Step 4: Verifică tracker-ul de echipă neatins**

Run: `python -m pytest tests/test_flask_routes.py -v` și deschide `/team` vizual.
Expected: identic cu înainte (acest plan nu atinge `analytics.py`/`team.html`).

- [ ] **Step 5: Commit final + actualizează STATUS**

Actualizează `context/STATUS.md` cu livrarea modulului de bonus redesign (dată, ce s-a livrat).
```bash
git add context/STATUS.md
git commit -m "docs(status): modul bonus redesign livrat"
```

---

## Self-Review Notes (verificare plan vs spec)

- **Spec §pagini** → Task 9 (tracker), 10 (obiective), 11 (drill-down), 12 (închidere), 13 (config), 14 (export). ✓
- **Spec §model KPI** (7 tipuri) → Task 5 (vanzari/marja/clienti/brand auto), 6 (clienti_noi_gama), 8 (`_actual_for_kpi` mapează incasari/scriptic manual). ✓
- **Spec §calcul (grilă, gate 80%)** → Task 2-3. ✓
- **Spec §model date (5 tabele + realizat_manual + istoric)** → Task 1, 7. ✓
- **Spec §5 game pre-încărcate + selector 9 game** → Task 10 (`DEFAULT_GAME`, `ALL_GAME`). ✓
- **Spec §PY +20% editabil** → Task 10 (`_proposed_kpis`). ✓
- **Spec §roster configurabil, Teo eliminat** → Task 1 (seed/delete), 13 (UI add/disable). ✓
- **Spec §flux închidere cu lock** → Task 12. ✓
- **Spec §team tracker neatins** → Task 16 step 4 verifică. ✓
- **Spec §risc migrare PRESETS→DB** → Task 15 (retragere după verde), 16 (regresie). ✓
- **Type consistency:** `build_agent_month` întoarce dict cu `kpis`/`scor`/`total_bonus`/`monthly_bonus`/`inchis`; consumat identic în Task 9/12/14. KPI dict canonic ({tip,referinta,target,unitate,pondere,actual,id}) consistent între queries (Task 4-7), motor (Task 3) și orchestrare (Task 8). ✓
- **Atenție execuție:** confirmă numele funcției de scriere din `app/db.py` (Task 4 step 4) — planul presupune `execute`; dacă diferă, înlocuiește global.
