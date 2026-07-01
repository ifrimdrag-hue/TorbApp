# Organsia Virtual Brand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "Organsia" as a fourth Basilur-family virtual brand, derived from the `B.ECO ORGANSIA` SKU-name prefix, mirroring the existing KingsLeaf/Tipson pattern.

**Architecture:** Prefix-based derivation duplicated across the three ETL import modules (no shared abstraction — follows existing style), a versioned migration to seed lead-time config + backfill historical rows, report/export constants extended to include Organsia, and a cosmetic sweep of AI-prompt/dropdown touchpoints. Documentation of the virtual-brand logic added to `.claude/project_knowledge.md`.

**Tech Stack:** Python 3.11, Flask, SQLite, pytest, ruff.

## Global Constraints

- **Rule ordering:** the `B.ECO ORGANSIA` check MUST precede the generic `B.` → Basilur check in every derivation function (subset prefix).
- **ruff:** all Python must pass `ruff check .` with zero errors (auto-fix hook runs on write).
- **Romanian encoding:** preserve UTF-8 diacritics in strings (ă, â, î, ș, ț) — see `.claude/project_knowledge.md` §Encoding.
- **Migration contract:** `up(conn)` must NOT call `conn.commit()`; export `VERSION: int` and `NAME: str`.
- **Idempotency:** all backfill UPDATEs filter `WHERE furnizor='Basilur' AND ... LIKE 'B.ECO ORGANSIA%'` so re-running is a no-op.
- **Canonical brand string:** `"Organsia"` (exact casing) everywhere; lowercase `"organsia"` only in `known_brand_keywords`.

---

### Task 1: Core prefix derivation + regression tests

**Files:**
- Modify: `etl/import_stoc.py` (`derive_furnizor`, `derive_gama`)
- Modify: `etl/import_vanzari_erp.py` (`_furnizor_from_prefix`)
- Modify: `etl/import_vanzari_tobra_auchan.py` (`derive_furnizor`)
- Modify: `etl/update_data.py` (`GAMA_MAP`)
- Test: `tests/test_derive_furnizor.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `derive_furnizor(sku, ...)` in `import_stoc`/`import_vanzari_tobra_auchan` and `_furnizor_from_prefix(sku)` in `import_vanzari_erp` return `"Organsia"` for `B.ECO ORGANSIA*` SKUs.

- [ ] **Step 1: Write the failing test**

Create `tests/test_derive_furnizor.py`:

```python
import importlib.util
import os

ETL = os.path.join(os.path.dirname(__file__), "..", "etl")


def _load(module_file):
    path = os.path.join(ETL, module_file)
    spec = importlib.util.spec_from_file_location(module_file[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stoc():
    return _load("import_stoc.py").derive_furnizor


def _erp():
    return _load("import_vanzari_erp.py")._furnizor_from_prefix


def _tobra():
    return _load("import_vanzari_tobra_auchan.py").derive_furnizor


ORGANSIA_SKU = "B.ECO ORGANSIA APPLE CINNAMON AND ROSEHIP 1,8GX18E 19322"
BASILUR_SKU = "B.CEYLON GOLD 100G"
KL_SKU = "KL SOME GREEN TEA"
TS_SKU = "TS SOME BLACK TEA"


def test_stoc_organsia():
    assert _stoc()(ORGANSIA_SKU) == "Organsia"

def test_stoc_basilur_unaffected():
    assert _stoc()(BASILUR_SKU) == "Basilur"

def test_stoc_kl_ts_unaffected():
    f = _stoc()
    assert f(KL_SKU) == "KingsLeaf"
    assert f(TS_SKU) == "Tipson"

def test_erp_organsia():
    assert _erp()(ORGANSIA_SKU) == "Organsia"

def test_erp_basilur_unaffected():
    assert _erp()(BASILUR_SKU) == "Basilur"

def test_tobra_organsia():
    assert _tobra()(ORGANSIA_SKU) == "Organsia"

def test_tobra_basilur_unaffected():
    assert _tobra()(BASILUR_SKU) == "Basilur"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_derive_furnizor.py -v`
Expected: FAIL — organsia tests return `"Basilur"` instead of `"Organsia"`.

- [ ] **Step 3: Add the Organsia rule to all three derivation functions**

In `etl/import_stoc.py` `derive_furnizor`, immediately BEFORE the `if s.startswith("B.") ...` line, add:

```python
    if s.upper().startswith("B.ECO ORGANSIA"):
        return "Organsia"
```

In `etl/import_stoc.py` `derive_gama` `gama_map`, add after the `"Basilur"` entry:

```python
        "Organsia":  "Organsia",
```

In `etl/import_vanzari_erp.py` `_furnizor_from_prefix`, immediately BEFORE the `if s.startswith("B.") ...` line, add:

```python
    if s.upper().startswith("B.ECO ORGANSIA"):
        return "Organsia"
```

In `etl/import_vanzari_tobra_auchan.py` `derive_furnizor`, immediately BEFORE the `if s.startswith("B.") ...` line, add:

```python
    if s.upper().startswith("B.ECO ORGANSIA"):
        return "Organsia"
```

In `etl/update_data.py` `GAMA_MAP`, add after the `"Basilur"` entry:

```python
    "Organsia":  "Organsia",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_derive_furnizor.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Lint + commit**

```bash
ruff check etl/ tests/test_derive_furnizor.py
git add etl/import_stoc.py etl/import_vanzari_erp.py etl/import_vanzari_tobra_auchan.py etl/update_data.py tests/test_derive_furnizor.py
git commit -m "feat(etl): derive Organsia virtual brand from B.ECO ORGANSIA prefix"
```

---

### Task 2: `produse` pricing-import override + rebuild_db seed

**Files:**
- Modify: `etl/import_preturi.py` (`import_monitorizare`)
- Modify: `etl/rebuild_db.py` (`termene_aprovizionare` seed loop, ~line 506)

**Interfaces:**
- Consumes: nothing.
- Produces: pricing import tags `B.ECO ORGANSIA*` products as `furnizor='Organsia'`; fresh DB rebuilds seed an Organsia lead-time row.

- [ ] **Step 1: Override furnizor/brand in import_monitorizare**

In `etl/import_preturi.py`, inside the `for row in rows[1:]:` loop of `import_monitorizare`, AFTER the lines that set `furnizor` and `brand` (currently lines ~103-104) and BEFORE `descriere` is used for the products dict, add:

```python
        if str(descriere).upper().startswith("B.ECO ORGANSIA"):
            furnizor = "Organsia"
            brand = "Organsia"
```

Note: `descriere` is assigned at line ~105 (`descriere= str(row[col['Produs']] ...)`). Move the new block to immediately AFTER the `descriere=` assignment so `descriere` is defined. Also update `origem, tip_origine = SUPPLIER_ORIGIN.get(furnizor, ...)` — it already handles `Organsia` (present in `SUPPLIER_ORIGIN`), so keep it AFTER the override.

Concretely, the order becomes:
```python
        descriere= str(row[col['Produs']] or '').strip()
        if str(descriere).upper().startswith("B.ECO ORGANSIA"):
            furnizor = "Organsia"
            brand = "Organsia"
        categorie= ...
        moneda   = ...
        ...
        origem, tip_origine = SUPPLIER_ORIGIN.get(furnizor, ('', 'import_extraeu'))
```

- [ ] **Step 2: Add Organsia to rebuild_db lead-time seed**

In `etl/rebuild_db.py`, in the seed list starting at line ~506, add after the `Tipson` entry:

```python
        ('Organsia',   120, 1, 'Produse sezoniere Crăciun — comandă Apr-Mai'),
```

- [ ] **Step 3: Verify syntax + lint**

Run: `python -c "import ast; ast.parse(open('etl/import_preturi.py',encoding='utf-8').read()); ast.parse(open('etl/rebuild_db.py',encoding='utf-8').read()); print('OK')"`
Then: `ruff check etl/import_preturi.py etl/rebuild_db.py`
Expected: `OK` and no ruff errors.

- [ ] **Step 4: Commit**

```bash
git add etl/import_preturi.py etl/rebuild_db.py
git commit -m "feat(etl): tag Organsia in pricing import + seed its lead time on rebuild"
```

---

### Task 3: Migration 0012 — seed lead time + backfill historical rows

**Files:**
- Create: `migrations/0012_20260701_organsia_brand.py`

**Interfaces:**
- Consumes: existing tables `termene_aprovizionare`, `stoc`, `tranzactii`, `produse`.
- Produces: reclassified historical rows and an Organsia `termene_aprovizionare` row in `data/torb.db`.

- [ ] **Step 1: Write the migration**

Create `migrations/0012_20260701_organsia_brand.py`:

```python
"""
Migration 0012 — Organsia virtual brand.

Seed termene_aprovizionare lead time for Organsia (mirror Basilur: 120 zile,
sezon Crăciun, USD, Ceai) and reclassify historical rows currently mis-tagged
as Basilur (SKUs whose name starts with 'B.ECO ORGANSIA') across stoc,
tranzactii and produse. Idempotent.
"""

VERSION = 12
NAME = "0012_20260701_organsia_brand"


def up(conn):
    conn.execute(
        "INSERT OR IGNORE INTO termene_aprovizionare "
        "(furnizor, zile_livrare, sezon_craciun, observatii, zile_livrare_min, moneda, tip_produs) "
        "VALUES ('Organsia', 120, 1, 'Produse sezoniere Crăciun — comandă Apr-Mai', 120, 'USD', 'Ceai')"
    )
    conn.execute(
        "UPDATE stoc SET furnizor='Organsia' "
        "WHERE furnizor='Basilur' AND sku LIKE 'B.ECO ORGANSIA%'"
    )
    conn.execute(
        "UPDATE stoc SET gama='Organsia' "
        "WHERE furnizor='Organsia' AND (gama IS NULL OR gama='Basilur')"
    )
    conn.execute(
        "UPDATE tranzactii SET furnizor='Organsia' "
        "WHERE furnizor='Basilur' AND sku LIKE 'B.ECO ORGANSIA%'"
    )
    conn.execute(
        "UPDATE produse SET furnizor='Organsia', brand='Organsia', gama='Organsia' "
        "WHERE furnizor='Basilur' AND descriere LIKE 'B.ECO ORGANSIA%'"
    )
```

- [ ] **Step 2: Back up the DB, then run the migration**

```bash
python etl/backup_db.py || cp data/torb.db data/torb.db.bak
python migrations/runner.py data/torb.db
```
Expected: `Applying 0012 ... 0012 OK.`

- [ ] **Step 3: Verify the backfill**

Run:
```bash
python -c "import sys,sqlite3; sys.stdout.reconfigure(encoding='utf-8'); c=sqlite3.connect('data/torb.db'); print('stoc', c.execute(\"SELECT COUNT(*) FROM stoc WHERE furnizor='Organsia'\").fetchone()[0]); print('tranz', c.execute(\"SELECT COUNT(*) FROM tranzactii WHERE furnizor='Organsia'\").fetchone()[0]); print('produse', c.execute(\"SELECT COUNT(*) FROM produse WHERE furnizor='Organsia'\").fetchone()[0]); print('leftover_basilur_organsia', c.execute(\"SELECT COUNT(*) FROM tranzactii WHERE furnizor='Basilur' AND sku LIKE 'B.ECO ORGANSIA%'\").fetchone()[0]); print('termene', c.execute(\"SELECT zile_livrare FROM termene_aprovizionare WHERE furnizor='Organsia'\").fetchone())"
```
Expected: stoc ≈ 20, tranz ≈ 718, produse ≥ 8, leftover_basilur_organsia = 0, termene = (120,).

- [ ] **Step 4: Commit**

```bash
ruff check migrations/0012_20260701_organsia_brand.py
git add migrations/0012_20260701_organsia_brand.py
git commit -m "feat(db): migration 0012 — seed Organsia lead time + backfill history"
```

---

### Task 4: Report & export layer

**Files:**
- Modify: `app/queries/forecast.py` (`BASILUR_BRANDS`, `_BASILUR_IN` — ~lines 480-481)
- Modify: `app/blueprints/reports.py` (`BASILUR_BRANDS` — ~line 330)
- Modify: `app/exports/ppt_export.py` (`BRANDS`, `BRAND_COLORS`, footer strings — ~lines 644-649, 673, 757)
- Modify: `app/templates/raportare_basilur.html`

**Interfaces:**
- Consumes: `furnizor='Organsia'` rows now present in DB (Task 3).
- Produces: Organsia appears as a fourth brand in KPI cards, stock table, monthly chart, Excel and PPT exports.

- [ ] **Step 1: Extend query constants**

In `app/queries/forecast.py`:
```python
BASILUR_BRANDS = ('Basilur', 'KingsLeaf', 'Tipson', 'Organsia')
_BASILUR_IN    = "('Basilur','KingsLeaf','Tipson','Organsia')"
```

- [ ] **Step 2: Extend blueprint constant**

In `app/blueprints/reports.py` line ~330:
```python
BASILUR_BRANDS = ['Basilur', 'KingsLeaf', 'Tipson', 'Organsia']
```

- [ ] **Step 3: Extend PPT export**

In `app/exports/ppt_export.py` `build_basilur_ppt`:
```python
    BRANDS = ["Basilur", "KingsLeaf", "Tipson", "Organsia"]
    BRAND_COLORS = [
        RGBColor(0x0d, 0x6e, 0xfd),
        RGBColor(0x19, 0x87, 0x54),
        RGBColor(0xfd, 0x7e, 0x14),
        RGBColor(0x6f, 0x42, 0xc1),
    ]
```
Update both footer strings (line ~673 and ~757) from
`"Basilur Group  •  Basilur  •  KingsLeaf  •  Tipson"` /
`"Basilur  •  KingsLeaf  •  Tipson"` to append `  •  Organsia`.

- [ ] **Step 4: Extend the HTML template**

In `app/templates/raportare_basilur.html`:
- Line ~46 `brand_colors`: add `, 'Organsia': '#6f42c1'`.
- Remove the header note (lines ~13-14): the `Organsia*` warning span. Replace the header brand line with `Basilur Group &mdash; Basilur &middot; KingsLeaf &middot; Tipson &middot; Organsia`.
- Lines ~239-241 JS arrays:
```javascript
  const BRANDS   = ['Basilur', 'KingsLeaf', 'Tipson', 'Organsia'];
  const COLORS   = ['#0d6efd', '#198754', '#fd7e14', '#6f42c1'];
  const ALPHAS   = ['rgba(13,110,253,0.18)', 'rgba(25,135,84,0.18)', 'rgba(253,126,20,0.18)', 'rgba(111,66,193,0.18)'];
```
- Remove the footnote paragraph (lines ~226-230) explaining Organsia is not imported.

- [ ] **Step 5: Smoke-test the report renders**

Run: `python -c "import sys; sys.path.insert(0,'app'); from app import create_app" 2>&1 | head -5 || true`
Then verify Jinja/py syntax by importing:
`python -c "import ast; ast.parse(open('app/queries/forecast.py',encoding='utf-8').read()); ast.parse(open('app/blueprints/reports.py',encoding='utf-8').read()); ast.parse(open('app/exports/ppt_export.py',encoding='utf-8').read()); print('OK')"`
Expected: `OK`. (Full app run happens in Task 6 verification.)

- [ ] **Step 6: Lint + commit**

```bash
ruff check app/queries/forecast.py app/blueprints/reports.py app/exports/ppt_export.py
git add app/queries/forecast.py app/blueprints/reports.py app/exports/ppt_export.py app/templates/raportare_basilur.html
git commit -m "feat(reports): include Organsia in Basilur-family report and exports"
```

---

### Task 5: Full sweep — dropdowns, AI prompts, forecast agent

**Files:**
- Modify: `app/blueprints/bonus.py` (`ALL_GAME`)
- Modify: `app/automations/ai/campaign_generator.py` (prompt + `known_brand_keywords`)
- Modify: `app/automations/ai/post_generator.py`, `app/automations/ai/claude_client.py`, `app/automations/auto_posts/generator.py`, `app/automations/pachete/ai_suggestions.py` (prompt copy)
- Modify: `app/templates/postari/facebook.html`, `app/templates/postari/instagram.html` (dropdown option)
- Modify: `app/forecast/forecast_agent.py` (lead-time / seasonality note)

**Interfaces:**
- Consumes: nothing structural.
- Produces: Organsia selectable/known across UI dropdowns and AI context.

- [ ] **Step 1: bonus dropdown list**

`app/blueprints/bonus.py` line ~20-21:
```python
ALL_GAME = ['Basilur', 'Toras', 'Celmar', 'Leonex', 'Delaviuda',
            'KingsLeaf', 'Solvex', 'Tipson', 'Cosmetice', 'Organsia']
```

- [ ] **Step 2: campaign_generator (prompt + keywords)**

In `app/automations/ai/campaign_generator.py`: add `- Organsia (ceaiuri bio)` to the brand bullet list near line ~26. In `known_brand_keywords` (~line 223) add `"organsia"` (lowercase):
```python
    known_brand_keywords = ["basilur", "kingsleaf", "tipson", "organsia", "torras", "celmar",
                            "delaviuda", "almendro", "leonex", "miss magic"]
```

- [ ] **Step 3: prompt-copy files**

Append `Organsia` (or `, Organsia`) to the tea-brand list in each:
- `app/automations/ai/post_generator.py` line ~25: `- Ceaiuri premium: Basilur, Kingsleaf, Tipson, Organsia`
- `app/automations/ai/claude_client.py` line ~24: `- Ceaiuri premium: Basilur (Sri Lanka), Kingsleaf, Tipson, Organsia`
- `app/automations/auto_posts/generator.py` line ~25: add `Organsia` to the tea list.
- `app/automations/pachete/ai_suggestions.py` line ~18: `- Ceaiuri premium: Basilur (Sri Lanka), Kingsleaf, Tipson, Organsia, Celmar (marca proprie)`

- [ ] **Step 4: post dropdowns**

In both `app/templates/postari/facebook.html` and `app/templates/postari/instagram.html` line ~35, append after the Tipson option:
```html
<option>Organsia</option>
```

- [ ] **Step 5: forecast_agent lead-time note**

In `app/forecast/forecast_agent.py` line ~20 and ~25, add Organsia alongside Basilur/Kings Leaf/Tipson:
```
- Basilur, Kings Leaf, Tipson, Organsia: 4 luni (120 zile) — import extraeuropean
...
- Produse Crăciun (Basilur, Kings Leaf, Tipson, Organsia): vârf de vânzări Oct-Nov
```

- [ ] **Step 6: Lint + commit**

```bash
ruff check app/blueprints/bonus.py app/automations/
git add app/blueprints/bonus.py app/automations/ app/templates/postari/ app/forecast/forecast_agent.py
git commit -m "feat: add Organsia to brand dropdowns, AI prompts, and forecast agent"
```

---

### Task 6: Documentation of virtual-brand logic

**Files:**
- Modify: `.claude/project_knowledge.md` (add a `## Virtual brands` section)

**Interfaces:**
- Consumes: nothing.
- Produces: a searchable, read-on-demand reference documenting all three virtual brands.

- [ ] **Step 1: Add the section**

Append a new section to `.claude/project_knowledge.md` (before `## Tech-debt`), documenting the virtual-brand derivation for KingsLeaf, Tipson, and Organsia:

```markdown
## Virtual brands (KingsLeaf, Tipson, Organsia)

`KingsLeaf`, `Tipson`, and `Organsia` are **virtual sub-brands of Basilur** — they
are not distinct ERP suppliers. All three ship from Basilur (Sri Lanka) on the same
PFI/shipment and are split out at import time from the SKU descriptive name prefix:

| Brand     | SKU-name prefix    | Notes |
|-----------|--------------------|-------|
| KingsLeaf | `KL ` (KL + space) | ERP product code range 90xxx |
| Tipson    | `TS ` (TS + space) | ERP product code range 80xxx |
| Organsia  | `B.ECO ORGANSIA`   | Subset of the `B.` Basilur prefix — MUST be checked BEFORE the generic `B.` rule |

**Where the rule lives (duplicated by design — no shared module):**
- `etl/import_stoc.py` — `derive_furnizor()` + `derive_gama()`
- `etl/import_vanzari_erp.py` — `_furnizor_from_prefix()`
- `etl/import_vanzari_tobra_auchan.py` — `derive_furnizor()`
- `etl/import_preturi.py` — `import_monitorizare()` overrides furnizor for the `produse` table (pricing spreadsheet lacks the split)
- `etl/update_data.py` + `etl/rebuild_db.py` — `GAMA_MAP` / lead-time seed

**Rolled into "Basilur family" reports:** the four brands are grouped via
`BASILUR_BRANDS` / `_BASILUR_IN` in `app/queries/forecast.py`, `BASILUR_BRANDS`
in `app/blueprints/reports.py`, and `BRANDS` in `app/exports/ppt_export.py`.
The Basilur report template is `app/templates/raportare_basilur.html`.

**Lead time:** all four share Basilur's 120-day (4-month) extra-EU lead time and
Christmas seasonality — seeded in `termene_aprovizionare`.

**Adding another virtual brand:** add the prefix rule to the three ETL derivation
functions (before the generic `B.` check if it's a `B.` subset), add to `GAMA_MAP`
and the `rebuild_db.py` seed, write a migration to seed `termene_aprovizionare`
and backfill existing `stoc`/`tranzactii`/`produse` rows, then extend the
`BASILUR_BRANDS` constants + template colors. See migration `0012` for the
Organsia example.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/project_knowledge.md
git commit -m "docs: document virtual-brand derivation (KingsLeaf/Tipson/Organsia)"
```

---

### Task 7: Full verification

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -q`
Expected: all pass (existing tests + new `test_derive_furnizor.py`).

- [ ] **Step 2: Lint the whole tree**

Run: `ruff check .`
Expected: no errors.

- [ ] **Step 3: Verify the report route renders with real data**

Start the app and load `/raportare-basilur`, confirm Organsia appears as a fourth
brand card with non-zero sales/stock and in the chart. (Use the `/run` skill or
manual launch per project convention.)

- [ ] **Step 4: Update STATUS.md**

Add a line to `context/STATUS.md` recording Organsia virtual brand delivered on 2026-07-01. Commit.
```
```

## Self-Review Notes

- **Spec coverage:** every spec scope item (§1 core derivation, §2 migration, §3 report/export, §4 full sweep, §5 tests) maps to Tasks 1–5; documentation request maps to Task 6. ✓
- **Ordering constraint** repeated in each derivation step. ✓
- **Type consistency:** `BASILUR_BRANDS` is a tuple in `forecast.py`, list in `reports.py` (matches existing pre-change types — intentional, not a bug). ✓
- **Color** `#6f42c1` (purple) used consistently across template + PPT. ✓
