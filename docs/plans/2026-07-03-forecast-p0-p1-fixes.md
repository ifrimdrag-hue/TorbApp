# Forecast Page P0/P1 Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 10 lowest-risk, well-specified findings from `docs/analysis/forecast_page_analysis.md` (items A1, A3, A4, A5, B1, B2, B3, B6, C1, C3, C5) without touching the higher-risk status-migration (A2) or the algorithm-quality items (B4/B5/B7/B8) or the D-DUP refactor.

**Architecture:** Each task is an isolated, mechanical fix to one of three files: `app/queries/forecast.py`, `app/forecast/forecast_logic.py`, `app/blueprints/forecast.py`, or `app/templates/forecast.html`. Python-side fixes get a pytest regression test (none currently exist for this surface — `tests/test_forecast_engine.py` covers a different, unrelated module). JS-only fixes (B3, part of A4/C1) have no test harness in this repo and are flagged for manual browser verification instead.

**Tech Stack:** Flask, SQLite (`db.query`/`db.query_one`/`db.get_db()`), pytest, Jinja2, vanilla JS.

## Global Constraints

- All Python must pass `ruff check .` with zero errors (auto-fix hook runs on every edit — no manual pass needed).
- English in code/comments/commits; Romanian in UI strings.
- Do not touch mojibake/encoding issues (D2) with the Edit tool — out of scope for this plan.
- Do not modify `/api/comenzi/<id>/status`, the status vocabulary, or any capitalized/lowercase status matching — that's A2, explicitly deferred.
- Tests use the existing `tests/conftest.py` fixtures: session-scoped `db_path` (temp SQLite built via `migrations/runner.py`) and `client` (authenticated Flask test client). Each test must use a **unique `furnizor`/SKU namespace** (e.g. `'TestBrandA5'`, `'SKU-A5-001'`) to avoid colliding with other tests sharing the same session DB.
- Run tests with: `python -m pytest tests/test_forecast_engine.py tests/test_flask_routes.py tests/test_forecast_queries.py -v` (new file `tests/test_forecast_queries.py` created in Task 3).

---

### Task 1: A3 — delete dead `/avanseaza` endpoint

**Files:**
- Modify: `app/blueprints/forecast.py:497-513` (delete the whole `api_comanda_avanseaza` route)
- Test: `tests/test_flask_routes.py`

**Interfaces:** None — pure deletion, no other code calls this endpoint (confirmed via grep of templates).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_flask_routes.py`:

```python
def test_comanda_avanseaza_endpoint_removed(client):
    """A3: dead /avanseaza endpoint was deleted — route no longer exists."""
    resp = client.post('/api/comenzi/1/avanseaza')
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_flask_routes.py::test_comanda_avanseaza_endpoint_removed -v`
Expected: FAIL (currently returns 500, since `queries.query_one` doesn't exist → AttributeError → Flask 500, or if comanda_id 1 doesn't exist, it hits `queries.query_one` before the 404 check and still raises AttributeError → 500 either way)

- [ ] **Step 3: Delete the endpoint**

In `app/blueprints/forecast.py`, delete lines 497-513:

```python
@forecast_bp.route('/api/comenzi/<int:comanda_id>/avanseaza', methods=['POST'])
def api_comanda_avanseaza(comanda_id):
    flow = ['Emisa', 'Confirmata', 'In tranzit', 'Receptionata']
    cmd  = queries.query_one("SELECT status FROM comenzi_furnizori WHERE id=?", (comanda_id,))
    if not cmd:
        return jsonify({'error': 'not found'}), 404
    current = cmd['status']
    if current in flow and flow.index(current) < len(flow) - 1:
        next_status = flow[flow.index(current) + 1]
        conn = db.get_db()
        try:
            conn.execute("UPDATE comenzi_furnizori SET status=? WHERE id=?",
                         (next_status, comanda_id))
            conn.commit()
        finally:
            conn.close()
    return redirect(url_for('forecast.forecast', tab='comenzi'))
```

Remove it entirely (keep the blank lines around it consistent with surrounding style).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_flask_routes.py::test_comanda_avanseaza_endpoint_removed -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/blueprints/forecast.py tests/test_flask_routes.py
git commit -m "fix(forecast): remove dead /avanseaza endpoint (A3)"
```

---

### Task 2: A1 — export client codes (data fix + validation)

**Files:**
- Modify: `app/blueprints/forecast.py:209-241` (`api_clienti_export_add`)
- Test: `tests/test_flask_routes.py`
- Data fix: run directly against `data/torb.db` (not committed — see Step 1)

**Interfaces:**
- Consumes: `tranzactii.cod_client` (existing table)
- Produces: `api_clienti_export_add` now returns `400 {'error': '...'}` when `cod_client` has zero matching rows in `tranzactii`

- [ ] **Step 1: Back up and patch the live data**

Live DB check already confirmed (2026-07-03): `clienti_export` has `cod_client='BRANDMIX'` / `'HUNTRADE'`, but `tranzactii.cod_client` for those clients is `'1429'` (BRANDMIX KFT) / `'1430'` (HUN-TRADE KFT).

```bash
python etl/backup_db.py
python -c "
import sqlite3
conn = sqlite3.connect('data/torb.db')
conn.execute(\"UPDATE clienti_export SET cod_client='1429' WHERE cod_client='BRANDMIX'\")
conn.execute(\"UPDATE clienti_export SET cod_client='1430' WHERE cod_client='HUNTRADE'\")
conn.commit()
print(conn.execute('SELECT cod_client, nume_client FROM clienti_export').fetchall())
conn.close()
"
```

Expected output: `[('1429', 'BrandMix'), ('1430', 'Hun-Trade')]`

- [ ] **Step 2: Write the failing test**

Add to `tests/test_flask_routes.py`:

```python
def test_clienti_export_add_rejects_unknown_code(client):
    """A1: adding an export client with a code absent from tranzactii is rejected."""
    resp = client.post('/api/clienti-export', json={
        'cod_client': 'NOSUCHCODE', 'client': 'Ghost Client', 'tara': 'HU',
    })
    d = resp.get_json()
    assert resp.status_code == 400
    assert d['ok'] is False or 'error' in d

def test_clienti_export_add_accepts_known_code(client):
    """A1: a code present in tranzactii (seeded 'C001') is accepted."""
    resp = client.post('/api/clienti-export', json={
        'cod_client': 'C001', 'client': 'Client Test', 'tara': 'HU',
    })
    d = resp.get_json()
    assert resp.status_code == 200
    assert d['ok'] is True
    # cleanup so other tests aren't affected
    client.delete('/api/clienti-export/C001')
```

- [ ] **Step 3: Run tests to verify the rejection test fails**

Run: `python -m pytest tests/test_flask_routes.py::test_clienti_export_add_rejects_unknown_code -v`
Expected: FAIL (currently inserts unconditionally, returns 200)

- [ ] **Step 4: Add the validation**

In `app/blueprints/forecast.py`, inside `api_clienti_export_add` (starts at line 210), after computing `cod` (line 213), before the DB insert (line 226):

```python
        cod = str(d['cod_client']).strip()
        exists = db.query_one("SELECT 1 FROM tranzactii WHERE cod_client=:c LIMIT 1", {'c': cod})
        if not exists:
            return jsonify({'error': f'Codul de client "{cod}" nu apare în nicio tranzacție.'}), 400
        client = (d.get('client') or '').strip()
```

(This replaces the two-line block that starts `cod = str(d['cod_client']).strip()` / `client = (d.get('client') or '').strip()` with the three-line version above — insert the `exists` check between them.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_flask_routes.py::test_clienti_export_add_rejects_unknown_code tests/test_flask_routes.py::test_clienti_export_add_accepts_known_code -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/blueprints/forecast.py tests/test_flask_routes.py
git commit -m "fix(forecast): correct export client codes + reject unknown codes on insert (A1)"
```

Note: the data fix in Step 1 is **not** part of the git commit (data/torb.db is gitignored) — it's a one-time production data patch, already applied directly.

---

### Task 3: A5 — price join in `forecast_stoc_extended`

**Files:**
- Modify: `app/queries/forecast.py:219-264` (`forecast_stoc_extended` SQL + the two synthetic-row dict blocks at lines ~373-391 and ~431-449)
- Create: `tests/test_forecast_queries.py`

**Interfaces:**
- Produces: every row from `forecast_stoc_extended()` now has `pret_valuta` and `moneda_valuta` keys (previously absent, causing empty `data-pret`/`data-moneda` in the template)

- [ ] **Step 1: Write the failing test**

Create `tests/test_forecast_queries.py`:

```python
"""Regression tests for app/queries/forecast.py — forecast page fixes."""
import sqlite3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))


def _conn(db_path):
    return sqlite3.connect(db_path)


def test_forecast_stoc_extended_includes_price(db_path, client):
    conn = _conn(db_path)
    conn.execute("""
        INSERT INTO stoc (data_snapshot, cod_produs, cod_mare, sku, furnizor, gama,
                           cantitate, pret_achizitie, data_intrare)
        VALUES ('2026-07-01', 'A5-001', 'A5-001', 'SKU-A5-001', 'TestBrandA5', 'Ceai',
                100, 10.0, '2026-06-01')
    """)
    conn.execute("""
        INSERT INTO costuri_landing (an, sku, moneda, pret_achizitie_valuta)
        VALUES (2026, 'SKU-A5-001', 'EUR', 3.5)
    """)
    conn.commit()
    conn.close()

    import queries
    rows = queries.forecast_stoc_extended(furnizor='TestBrandA5')
    assert len(rows) == 1
    assert rows[0]['pret_valuta'] == 3.5
    assert rows[0]['moneda_valuta'] == 'EUR'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forecast_queries.py::test_forecast_stoc_extended_includes_price -v`
Expected: FAIL with `KeyError: 'pret_valuta'`

- [ ] **Step 3: Add the join and columns**

In `app/queries/forecast.py`, `forecast_stoc_extended` SELECT (lines 233-244), add two columns and a join, mirroring `forecast_stoc_brand` (lines 169-170, 177-178):

```python
    rows = query(f"""
        SELECT s.sku, MAX(s.cod_mare)                         AS cod_produs,
               s.furnizor, s.gama,
               SUM(s.cantitate)                               AS stoc_total,
               ROUND(SUM(s.cantitate * s.pret_achizitie), 2)  AS valoare_stoc,
               COALESCE(ROUND(v.vanzari_luna_avg, 1), 0)      AS vanzari_luna_avg,
               CASE WHEN COALESCE(v.vanzari_luna_avg, 0) > 0
                    THEN CAST(ROUND(SUM(s.cantitate) / (v.vanzari_luna_avg / 30.0)) AS INTEGER)
                    ELSE NULL END                              AS zile_stoc,
               MIN(s.data_intrare)                            AS cel_mai_vechi_lot,
               COALESCE(ROUND(v_split.avg_ro, 1), 0)          AS avg_monthly_ro,
               COALESCE(ROUND(v_split.avg_hu, 1), 0)          AS avg_monthly_hu,
               cl.pret_achizitie_valuta                       AS pret_valuta,
               cl.moneda                                      AS moneda_valuta
        FROM stoc s
        LEFT JOIN (
            SELECT sku, SUM(cantitate) / 3.0 AS vanzari_luna_avg
            FROM tranzactii WHERE data_dl >= date('now', '-90 days')
            GROUP BY sku
        ) v ON s.sku = v.sku
        LEFT JOIN (
            SELECT sku,
                   SUM(CASE WHEN cod_client NOT IN (SELECT cod_client FROM clienti_export WHERE activ=1)
                            THEN cantitate ELSE 0 END) / 3.0 AS avg_ro,
                   SUM(CASE WHEN cod_client IN (SELECT cod_client FROM clienti_export WHERE activ=1)
                            THEN cantitate ELSE 0 END) / 3.0 AS avg_hu
            FROM tranzactii WHERE data_dl >= date('now', '-90 days')
            GROUP BY sku
        ) v_split ON s.sku = v_split.sku
        LEFT JOIN costuri_landing cl ON cl.sku = s.sku
            AND cl.an = (SELECT MAX(an) FROM costuri_landing WHERE sku = s.sku)
        WHERE s.data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
          AND s.cantitate > 0 {where}
        GROUP BY s.sku, s.furnizor, s.gama
        ORDER BY zile_stoc ASC NULLS LAST, valoare_stoc DESC
    """, params)
```

Then in the two synthetic-row dict literals (transit-only block, currently ending `'lead_time_days': lead,` around line 390; and sold-but-absent block, currently ending `'lead_time_days': lead,` around line 448), add after `'cel_mai_vechi_lot': None,` / `'cel_mai_vechi_lot': None,` respectively:

```python
            'pret_valuta':       None,
            'moneda_valuta':     None,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forecast_queries.py::test_forecast_stoc_extended_includes_price -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/queries/forecast.py tests/test_forecast_queries.py
git commit -m "fix(forecast): join costuri_landing for price in forecast_stoc_extended (A5)"
```

---

### Task 4: B1 — `forecast_summary` counts SKUs, not lots

**Files:**
- Modify: `app/queries/forecast.py:55-85` (`forecast_summary`)
- Test: `tests/test_forecast_queries.py`

**Interfaces:**
- Produces: `forecast_summary()` — same keys (`nr_sku`, `valoare_totala`, `critic`, `atentie`, `ok`), but `critic+atentie+ok` now sums to `nr_sku` instead of to the lot count.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_forecast_queries.py`:

```python
def test_forecast_summary_counts_skus_not_lots(db_path, client):
    conn = _conn(db_path)
    # Same SKU, two lots (multi-lot SKU) — must count once, not twice
    conn.execute("""
        INSERT INTO stoc (data_snapshot, cod_produs, cod_mare, sku, furnizor, gama,
                           cantitate, pret_achizitie, data_intrare)
        VALUES ('2026-07-02', 'B1-001', 'B1-001', 'SKU-B1-MULTILOT', 'TestBrandB1', 'Ceai',
                10, 5.0, '2026-05-01')
    """)
    conn.execute("""
        INSERT INTO stoc (data_snapshot, cod_produs, cod_mare, sku, furnizor, gama,
                           cantitate, pret_achizitie, data_intrare)
        VALUES ('2026-07-02', 'B1-001', 'B1-001', 'SKU-B1-MULTILOT', 'TestBrandB1', 'Ceai',
                10, 5.0, '2026-06-01')
    """)
    conn.commit()
    conn.close()

    import queries
    summary = queries.forecast_summary()
    total_counted = (summary['critic'] or 0) + (summary['atentie'] or 0) + (summary['ok'] or 0)
    assert total_counted == summary['nr_sku'], (
        f"critic+atentie+ok ({total_counted}) must equal nr_sku ({summary['nr_sku']}) "
        "— a multi-lot SKU must count once"
    )
```

Note: `db_path`/`client` fixtures are session-scoped and other tests may have inserted `stoc` rows into the *latest* snapshot already — use a snapshot date (`'2026-07-02'`) that sorts after any other test's snapshot so `MAX(data_snapshot)` picks it up, or accept that this test only checks the *ratio* invariant (`total_counted == nr_sku`), which holds regardless of what else is in the latest snapshot. The assertion above already only depends on that invariant, not on absolute counts — safe as written.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forecast_queries.py::test_forecast_summary_counts_skus_not_lots -v`
Expected: FAIL — `total_counted` is inflated (counts 2 for the multi-lot SKU) while `nr_sku` counts 1, so with only this one SKU in the snapshot `total_counted=2 != nr_sku=1`.

- [ ] **Step 3: Rewrite the query to aggregate to SKU first**

Replace `forecast_summary` (lines 55-85) entirely:

```python
def forecast_summary():
    """KPI cards pentru pagina de forecast."""
    return query_one("""
        SELECT
            COUNT(*)                                                     AS nr_sku,
            ROUND(SUM(valoare_stoc), 0)                                  AS valoare_totala,
            SUM(CASE WHEN zile_stoc IS NOT NULL AND zile_stoc < 30  THEN 1 ELSE 0 END) AS critic,
            SUM(CASE WHEN zile_stoc IS NOT NULL AND zile_stoc BETWEEN 30 AND 59 THEN 1 ELSE 0 END) AS atentie,
            SUM(CASE WHEN zile_stoc IS NULL OR zile_stoc >= 60 THEN 1 ELSE 0 END) AS ok
        FROM (
            SELECT s.sku,
                SUM(s.cantitate * s.pret_achizitie) AS valoare_stoc,
                CASE
                    WHEN COALESCE(v.vanzari_luna_avg, 0) > 0
                    THEN CAST(ROUND(SUM(s.cantitate) / (v.vanzari_luna_avg / 30.0)) AS INTEGER)
                    ELSE NULL
                END AS zile_stoc
            FROM stoc s
            LEFT JOIN (
                SELECT sku, SUM(cantitate) / 3.0 AS vanzari_luna_avg
                FROM tranzactii
                WHERE data_dl >= date('now', '-90 days')
                GROUP BY sku
            ) v ON s.sku = v.sku
            WHERE s.data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
              AND s.cantitate > 0
            GROUP BY s.sku
        )
    """)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forecast_queries.py::test_forecast_summary_counts_skus_not_lots -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/queries/forecast.py tests/test_forecast_queries.py
git commit -m "fix(forecast): KPI cards aggregate to SKU level, not lot level (B1)"
```

---

### Task 5: B2 — `zile_stoc` in `forecast_stoc_extended` must exclude transit

**Files:**
- Modify: `app/queries/forecast.py` — three spots in `forecast_stoc_extended`: the main-row overwrite (~lines 328-334), the transit-only synthetic block (~line 371), and no change needed in the sold-but-absent block (already `zile_stoc: 0` by design)
- Test: `tests/test_forecast_queries.py`

**Interfaces:** No signature change — same dict keys, corrected values. The template's "Zile cu tranzit" column (`app/templates/forecast.html:198`) already independently computes the with-transit figure from `r.stoc_total + tranz` — **no template change needed**, confirmed by reading forecast.html:196-198,245.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_forecast_queries.py`:

```python
def test_zile_stoc_excludes_transit(db_path, client):
    conn = _conn(db_path)
    conn.execute("""
        INSERT INTO stoc (data_snapshot, cod_produs, cod_mare, sku, furnizor, gama,
                           cantitate, pret_achizitie, data_intrare)
        VALUES ('2026-07-03', 'B2-001', 'B2-001', 'SKU-B2-001', 'TestBrandB2', 'Ceai',
                30, 10.0, '2026-06-01')
    """)
    # 3 years of sales so the 3-year monthly average kicks in and overwrites zile_stoc
    for luna in range(1, 13):
        conn.execute("""
            INSERT INTO tranzactii (luna, an, data_dl, sku, furnizor, cantitate,
                                     cod_produs, client, cod_client, agent,
                                     pret_vanzare, tva_pct, pret_cumparare,
                                     val_bruta, val_neta, val_achizitie, marja_bruta, discount_pct)
            VALUES (:luna, 2025, '2025-' || printf('%02d', :luna) || '-10',
                    'SKU-B2-001', 'TestBrandB2', 30,
                    'B2-001', 'Client Test', 'C001', 'Agent Test',
                    10, 0.09, 5, 300, 275, 150, 125, 0)
        """, {'luna': luna})
    # An active in-transit order for the same SKU — must NOT reduce zile_stoc
    conn.execute("""
        INSERT INTO comenzi_furnizori (nr_comanda, furnizor, status, data_estimata_livrare)
        VALUES ('CMD-B2-1', 'TestBrandB2', 'confirmata', '2026-08-01')
    """)
    cid = conn.execute("SELECT id FROM comenzi_furnizori WHERE nr_comanda='CMD-B2-1'").fetchone()[0]
    conn.execute("""
        INSERT INTO comenzi_furnizori_linii (comanda_id, sku, cantitate_comandata)
        VALUES (?, 'SKU-B2-001', 30)
    """, (cid,))
    conn.commit()
    conn.close()

    import queries
    rows = queries.forecast_stoc_extended(furnizor='TestBrandB2')
    assert len(rows) == 1
    r = rows[0]
    # 30 avg/month sales -> daily rate 1/day -> stoc-only zile_stoc should be ~30 (30 buc / 1 buc/day)
    # If transit (30 more) were included, available=60 -> zile_stoc would be ~60
    assert r['zile_stoc'] < 45, (
        f"zile_stoc={r['zile_stoc']} appears to include the 30-unit in-transit order "
        "(physical stock alone should give ~30 days, not ~60)"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forecast_queries.py::test_zile_stoc_excludes_transit -v`
Expected: FAIL — `zile_stoc` computed from `available` (stock 30 + transit 30 = 60) is roughly double the physical-only figure.

- [ ] **Step 3: Fix the two overwrite sites**

In `app/queries/forecast.py`, main-row loop (around line 319-334), change:

```python
        available = float(r['stoc_total'] or 0) + float(r['in_tranzit_qty'] or 0)
        sug_ro = max(0.0, demand_ro - available)
        surplus = max(0.0, available - demand_ro)
        sug_hu = max(0.0, demand_hu - surplus)
```

Keep `available` as-is (it's correctly used for the RO/HU *suggestion* math — that's supposed to include transit). Only change the `zile_stoc` overwrite a few lines below:

```python
        avg_total = sum(monthly_total.values()) / 12 if monthly_total else 0
        r['avg_monthly_ro'] = round(sum(monthly_ro.values()) / 12, 1) if monthly_ro else 0
        r['avg_monthly_hu'] = round(sum(monthly_hu.values()) / 12, 1) if monthly_hu else 0
        r['vanzari_luna_avg'] = round(avg_total, 1)
        if avg_total > 0:
            r['zile_stoc'] = int(float(r['stoc_total'] or 0) / (avg_total / 30))
```

(Change `available` → `float(r['stoc_total'] or 0)` on that last line only.)

In the transit-only synthetic block (around line 371), change:

```python
        zile_stoc = int(available / (avg_total / 30)) if avg_total > 0 else None
```

to:

```python
        zile_stoc = 0 if avg_total > 0 else None
```

(These synthetic rows have `stoc_total = 0` by definition — physical-stock-only days is always 0 when there's any velocity, `None` when there's none. `available`/`transit_qty` remain used for the RO/HU suggestion math above this line, unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forecast_queries.py::test_zile_stoc_excludes_transit -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/queries/forecast.py tests/test_forecast_queries.py
git commit -m "fix(forecast): zile_stoc reflects physical stock only, not stock+transit (B2)"
```

---

### Task 6: B6 — coalesce `eta` with `data_estimata_livrare` in transit chips

**Files:**
- Modify: `app/queries/forecast.py:271` (transit query inside `forecast_stoc_extended`)
- Test: `tests/test_forecast_queries.py`

**Interfaces:** No change — same `in_tranzit[].eta` key, correct value.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_forecast_queries.py`:

```python
def test_transit_eta_prefers_eta_column(db_path, client):
    conn = _conn(db_path)
    conn.execute("""
        INSERT INTO stoc (data_snapshot, cod_produs, cod_mare, sku, furnizor, gama,
                           cantitate, pret_achizitie, data_intrare)
        VALUES ('2026-07-04', 'B6-001', 'B6-001', 'SKU-B6-001', 'TestBrandB6', 'Ceai',
                5, 10.0, '2026-06-01')
    """)
    conn.execute("""
        INSERT INTO comenzi_furnizori (nr_comanda, furnizor, status, data_estimata_livrare, eta)
        VALUES ('CMD-B6-1', 'TestBrandB6', 'confirmata', '2026-06-02', '2026-07-21')
    """)
    cid = conn.execute("SELECT id FROM comenzi_furnizori WHERE nr_comanda='CMD-B6-1'").fetchone()[0]
    conn.execute("""
        INSERT INTO comenzi_furnizori_linii (comanda_id, sku, cantitate_comandata)
        VALUES (?, 'SKU-B6-001', 10)
    """, (cid,))
    conn.commit()
    conn.close()

    import queries
    rows = queries.forecast_stoc_extended(furnizor='TestBrandB6')
    assert len(rows) == 1
    assert rows[0]['in_tranzit'][0]['eta'] == '2026-07-21', (
        "should prefer the newer `eta` column over the stale `data_estimata_livrare`"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forecast_queries.py::test_transit_eta_prefers_eta_column -v`
Expected: FAIL — returns `'2026-06-02'` (the stale `data_estimata_livrare`).

- [ ] **Step 3: Fix the query**

In `app/queries/forecast.py`, inside `forecast_stoc_extended`, the transit query (around line 270-281):

```python
    for r in query("""
        SELECT l.sku, c.nr_comanda, c.furnizor, COALESCE(c.eta, c.data_estimata_livrare) AS eta,
               MAX(l.cod_furnizor) AS cod_produs,
               SUM(COALESCE(l.cantitate_confirmata, l.cantitate_comandata)) AS qty
        FROM comenzi_furnizori_linii l
        JOIN comenzi_furnizori c ON c.id = l.comanda_id
        WHERE c.status IN ('In tranzit', 'Confirmata', 'Emisa',
                           'in_tranzit', 'confirmata', 'emisa')
          AND COALESCE(l.cantitate_confirmata, l.cantitate_comandata) > 0
        GROUP BY l.sku, c.nr_comanda, c.data_estimata_livrare
        ORDER BY l.sku, c.data_estimata_livrare
    """):
```

(Only the `SELECT` column changes: `c.data_estimata_livrare AS eta` → `COALESCE(c.eta, c.data_estimata_livrare) AS eta`. Leave `GROUP BY`/`ORDER BY` on `data_estimata_livrare` as-is — they only affect row ordering/grouping granularity, not correctness of the returned value.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forecast_queries.py::test_transit_eta_prefers_eta_column -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/queries/forecast.py tests/test_forecast_queries.py
git commit -m "fix(forecast): transit chips use eta column with data_estimata_livrare fallback (B6)"
```

---

### Task 7: C3 — parameterize export-codes SQL in `_monthly_sales_by_sku`

**Files:**
- Modify: `app/forecast/forecast_logic.py:86-114` (`_monthly_sales_by_sku`)
- Test: `tests/test_forecast_queries.py`

**Interfaces:** No signature change. `_monthly_sales_by_sku(furnizor: str) -> dict` keeps the same return shape.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_forecast_queries.py`:

```python
def test_monthly_sales_by_sku_survives_quote_in_export_code(db_path, client):
    conn = _conn(db_path)
    # A client code containing a single quote — breaks the old f-string-interpolated SQL
    conn.execute("""
        INSERT INTO clienti_export (tara_id, cod_client, nume_client, activ)
        VALUES (1, "O'BRIEN", 'OBrien Ltd', 1)
    """)
    conn.execute("""
        INSERT INTO tranzactii (luna, an, data_dl, sku, furnizor, cantitate,
                                 cod_produs, client, cod_client, agent,
                                 pret_vanzare, tva_pct, pret_cumparare,
                                 val_bruta, val_neta, val_achizitie, marja_bruta, discount_pct)
        VALUES (1, 2025, '2025-01-10', 'SKU-C3-001', 'TestBrandC3', 20,
                'C3-001', 'OBrien Ltd', "O'BRIEN", 'Agent Test',
                10, 0.09, 5, 200, 180, 100, 80, 0)
    """)
    conn.commit()
    conn.close()

    from forecast import forecast_logic
    result = forecast_logic._monthly_sales_by_sku('TestBrandC3')  # must not raise
    assert 'SKU-C3-001' in result
    assert result['SKU-C3-001']['export'].get(1) == 20, "sale should be attributed to export (O'BRIEN is active)"
    assert result['SKU-C3-001']['ro'].get(1, 0) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forecast_queries.py::test_monthly_sales_by_sku_survives_quote_in_export_code -v`
Expected: FAIL — `sqlite3.OperationalError` (malformed SQL from the unescaped `'` in `O'BRIEN`).

- [ ] **Step 3: Replace the f-string IN-list with a subselect**

In `app/forecast/forecast_logic.py`, replace lines 98-104:

```python
    export_codes = get_export_codes()
    if export_codes:
        placeholders = ",".join(f"'{str(c)}'" for c in export_codes)
        export_clause = f"cod_client IN ({placeholders})"
    else:
        # Fără clienți export configurați → toate vânzările sunt RO
        export_clause = "0"
```

with:

```python
    export_clause = "cod_client IN (SELECT cod_client FROM clienti_export WHERE activ = 1)"
```

(This matches the subselect pattern `forecast_stoc_extended` already uses for the same split, and is immune to special characters in `cod_client` since it's evaluated entirely in SQL — no Python string interpolation of user data.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forecast_queries.py::test_monthly_sales_by_sku_survives_quote_in_export_code -v`
Expected: PASS

- [ ] **Step 5: Run the full forecast test files to confirm no regression**

Run: `python -m pytest tests/test_forecast_engine.py tests/test_flask_routes.py tests/test_forecast_queries.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/forecast/forecast_logic.py tests/test_forecast_queries.py
git commit -m "fix(forecast): parameterize export-code filter in _monthly_sales_by_sku (C3)"
```

---

### Task 8: C5 — normalize `_listing_changes` SKU keys

**Files:**
- Modify: `app/forecast/forecast_logic.py:171-205` (`_listing_changes`)
- Test: `tests/test_forecast_queries.py`

**Interfaces:** `_listing_changes(furnizor: str) -> dict` — same shape, keys now normalized via `_normalize_sku` so they match `build_suggestion`'s lookup keys (`all_skus` at line 277, built from `monthly_data.keys()` which are already normalized).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_forecast_queries.py`:

```python
def test_listing_changes_keys_are_normalized(db_path, client):
    conn = _conn(db_path)
    # ERP-style bare-EAN SKU (no parens) — ERP sometimes exports it this way
    bare_sku = 'PRODUS TEST C5 1234567890123'
    conn.execute("""
        INSERT INTO tranzactii (luna, an, data_dl, sku, furnizor, cantitate,
                                 cod_produs, client, cod_client, agent,
                                 pret_vanzare, tva_pct, pret_cumparare,
                                 val_bruta, val_neta, val_achizitie, marja_bruta, discount_pct)
        VALUES (7, 2026, date('now', '-10 days'), :sku, 'TestBrandC5', 5,
                'C5-001', 'New Client', 'NEWC5', 'Agent Test',
                10, 0.09, 5, 50, 45, 25, 20, 0)
    """, {'sku': bare_sku})
    conn.commit()
    conn.close()

    from forecast import forecast_logic
    changes = forecast_logic._listing_changes('TestBrandC5')
    normalized = forecast_logic._normalize_sku(bare_sku)
    assert normalized in changes, (
        f"expected normalized key {normalized!r} in {list(changes.keys())} "
        "so build_suggestion's normalized-key lookup finds it"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_forecast_queries.py::test_listing_changes_keys_are_normalized -v`
Expected: FAIL — the dict is keyed by the raw bare-EAN SKU, not the normalized (parenthesized) form.

- [ ] **Step 3: Normalize the keys**

In `app/forecast/forecast_logic.py`, `_listing_changes`, change the return line (currently):

```python
        return {r['sku']: {'new': r['new_c'] or 0, 'lost': r['lost_c'] or 0} for r in rows}
```

to:

```python
        return {_normalize_sku(r['sku']): {'new': r['new_c'] or 0, 'lost': r['lost_c'] or 0} for r in rows}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_forecast_queries.py::test_listing_changes_keys_are_normalized -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/forecast/forecast_logic.py tests/test_forecast_queries.py
git commit -m "fix(forecast): normalize _listing_changes SKU keys to match lookup (C5)"
```

---

### Task 9: B3 — `saveOrder` must skip filtered-out (hidden) rows

**Files:**
- Modify: `app/templates/forecast.html:1122-1146` (`saveOrder`)

**Interfaces:** None — client-side only, no test harness exists for JS in this repo.

- [ ] **Step 1: Make the fix**

In `app/templates/forecast.html`, inside `saveOrder(status)` (starts at line 1122), the `forEach` callback (lines 1125-1146) currently starts:

```javascript
  document.querySelectorAll('#suggestTbody tr').forEach(row => {
    const idx = parseInt(row.dataset.idx);
```

Add the same guard `updateTotal()` already uses (line 1107):

```javascript
  document.querySelectorAll('#suggestTbody tr').forEach(row => {
    if (row.style.display === 'none') return;
    const idx = parseInt(row.dataset.idx);
```

- [ ] **Step 2: Manual browser verification (no automated JS test exists)**

1. Start the app (`python app/app.py` or the project's usual launcher).
2. Go to `/forecast`, tab "Sugestie Comandă", select a brand with ≥10 suggested SKUs.
3. Type a search term in the row filter that narrows to ~3 visible rows.
4. Confirm the footer total (`#suggestTotal`) only reflects the visible rows.
5. Click "Confirmă Comanda" (or draft), then open the created order in "Comenzi Furnizori" and confirm its line count/total matches what was visible in step 4, not the full unfiltered set.

- [ ] **Step 3: Commit**

```bash
git add app/templates/forecast.html
git commit -m "fix(forecast): saveOrder skips hidden/filtered rows to match displayed total (B3)"
```

---

### Task 10: A4 + C1 — harden `forecast.html` JS against unescaped data

**Files:**
- Modify: `app/templates/forecast.html` — four spots: `loadExportClients` (~1519-1537), `addExportClient` (~1543-1564), the status-modal trigger button (~534) + `openStatusModal` (~1330), `sendAgentMsg` (~1472-1505)

**Interfaces:** None — client-side only.

- [ ] **Step 1: Add a shared HTML-escape helper**

Near the top of the `<script>` block in `app/templates/forecast.html` (find the first `<script>` tag containing page JS — before `loadExportClients` is fine since functions are hoisted for `function` declarations, but this is a `const`, so place it above its first use, e.g. right before `loadExportClients`):

```javascript
function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s ?? '';
  return div.innerHTML;
}
```

- [ ] **Step 2: Fix `loadExportClients` — quote/escape `cod_client`, `client`, `observatii`**

Replace the `tbody.innerHTML = d.items.map(...)` block (lines 1519-1537):

```javascript
    tbody.innerHTML = d.items.map(c => `
      <tr class="${c.activ ? '' : 'text-muted'}">
        <td class="fw-semibold">${escapeHtml(c.cod_client)}</td>
        <td>${escapeHtml(c.client)}</td>
        <td class="text-center"><span class="badge bg-secondary">${escapeHtml(c.tara || '—')}</span></td>
        <td class="text-center">
          <div class="form-check form-switch d-flex justify-content-center">
            <input class="form-check-input" type="checkbox" ${c.activ ? 'checked' : ''}
                   data-cod="${escapeHtml(c.cod_client)}" data-client="${escapeHtml(c.client || '')}"
                   data-tara="${escapeHtml(c.tara || 'HU')}" data-obs="${escapeHtml(c.observatii || '')}"
                   onchange="toggleExportClient(this.dataset.cod, this.dataset.client, this.checked, this.dataset.tara, this.dataset.obs)">
          </div>
        </td>
        <td class="text-muted small">${escapeHtml(c.observatii || '—')}</td>
        <td>
          <button class="btn btn-sm btn-link text-danger p-0" data-cod="${escapeHtml(c.cod_client)}"
                  onclick="deleteExportClient(this.dataset.cod)" title="Șterge">
            <i class="bi bi-trash"></i>
          </button>
        </td>
      </tr>
    `).join('');
```

- [ ] **Step 3: Fix `addExportClient` — stop rejecting non-numeric codes**

Replace the first line of `addExportClient` (line 1544):

```javascript
  const cod = parseInt(document.getElementById('exportClientCod').value);
  if (!cod) { alert('Selectează un client din lista de sugestii.'); return; }
```

with:

```javascript
  const cod = document.getElementById('exportClientCod').value.trim();
  if (!cod) { alert('Selectează un client din lista de sugestii.'); return; }
```

- [ ] **Step 4: Fix the status-modal `onclick` to use `data-*` attributes**

In `app/templates/forecast.html:534`, replace:

```html
            <button class="btn btn-sm btn-outline-primary" onclick="openStatusModal({{ c.id }}, '{{ c.status }}', '{{ c.data_estimata_livrare or '' }}', '{{ c.data_confirmare_furnizor or '' }}', `{{ c.observatii or '' }}`)">
```

with:

```html
            <button class="btn btn-sm btn-outline-primary" data-cid="{{ c.id }}" data-status="{{ c.status }}"
                    data-livrare="{{ c.data_estimata_livrare or '' }}" data-confirmare="{{ c.data_confirmare_furnizor or '' }}"
                    data-obs="{{ c.observatii or '' }}"
                    onclick="openStatusModal(this.dataset.cid, this.dataset.status, this.dataset.livrare, this.dataset.confirmare, this.dataset.obs)">
```

- [ ] **Step 5: Escape user/AI text in `sendAgentMsg`**

In `app/templates/forecast.html`, `sendAgentMsg` (lines 1472-1505), change the two `insertAdjacentHTML` calls that embed `q` and `answer`:

```javascript
  msgs.insertAdjacentHTML('beforeend',
    `<div class="d-flex justify-content-end mb-2">
       <div class="bg-primary text-white rounded px-2 py-1" style="max-width:80%">${escapeHtml(q)}</div>
     </div>`);
```

and further down:

```javascript
    const answer = d.answer || d.error || 'Eroare necunoscută.';
    msgs.insertAdjacentHTML('beforeend',
      `<div class="d-flex justify-content-start mb-2">
         <div class="bg-light border rounded px-2 py-1" style="max-width:90%;white-space:pre-wrap">${escapeHtml(answer)}</div>
       </div>`);
```

- [ ] **Step 6: Manual browser verification**

1. Go to `/forecast`, tab "Clienți Export". Add a client whose name (from autocomplete) or observation you type contains a backtick or `${x}` — confirm the row renders literally (no JS error in console, no execution).
2. Toggle the active switch and delete a row — confirm both still work (this exercises the new `data-*`-driven calls).
3. Open the Agent chat panel, type a message containing `<script>alert(1)</script>` — confirm it renders as literal text in the chat bubble, not executed.
4. Go to "Comenzi Furnizori", open an order with an observation containing a backtick, click "Actualizare Status" — confirm the modal opens and populates correctly (this exercises the `data-*` refactor of `openStatusModal`).

- [ ] **Step 7: Commit**

```bash
git add app/templates/forecast.html
git commit -m "fix(forecast): escape/quote user data in client-side HTML building (A4, C1)"
```

---

## Final verification (all tasks)

- [ ] Run `ruff check .` — zero errors.
- [ ] Run `python -m pytest tests/ -v` — full suite passes (not just the forecast files, to catch cross-module regressions).
- [ ] Manually verify Tasks 9 and 10 in the browser per their Step 2/6 checklists above (no automated coverage exists for JS).
- [ ] Confirm `data/torb.db`'s `clienti_export` table shows the corrected codes (Task 2, Step 1) — `SELECT cod_client, nume_client FROM clienti_export;`
