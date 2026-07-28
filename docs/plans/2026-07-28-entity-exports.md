# Entity Exports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the brand page Excel + PPT export and the produs page PPT export, on a shared context layer that keeps both formats period-correct and in sync.

**Architecture:** A new module `app/exports/entities.py` builds one context dict per entity (client, agent, brand, produs) containing both the Excel sheets and the PPT cards/tables/trend. `app/exports/ppt_export.py` gains a `_slide_kpi_tables` layout primitive that replaces the two near-duplicate detail-slide builders. `app/blueprints/reports.py` replaces its four named PPT endpoints with one `/export/ppt/<entity>` dispatcher that self-guards on the nav key, the same way `export_excel` already does.

**Tech Stack:** Flask, SQLite, `openpyxl`, `python-pptx`, pytest, ruff.

**Spec:** `docs/specs/2026-07-28-entity-exports-design.md`

## Global Constraints

- All Python must pass `ruff check .` with zero errors. Rules and version are pinned in `ruff.toml` / `requirements-dev.txt` — never unpin.
- Never use bare `except` (E722), multiple imports on one line (E401), imports below the top of the file (E402), or compound statements (E701/E702).
- Developer-facing text (code, comments, commit messages) in **English**. User-facing strings (slide titles, sheet names, table captions, button labels) in **Romanian**.
- Romanian text in `.py` files: read `docs/TECHNICAL.md` §Encoding **before** editing any `.py` that contains diacritics. Files are UTF-8; do not let an editor rewrite them as cp1252.
- Never add a raw `<a>` nav link to `base.html`. Nav links are registered in `app/nav_registry.py`.
- No new SQL queries. Every query this plan needs already exists and already accepts `luna`/`max_luna`.
- Test DB seed (from `tests/conftest.py`), used by every test below:
  - year `2026`, month `1` only
  - clients: `C001` ("Client Test"), `KAUFLAND` ("KAUFLAND ROMANIA")
  - agent: `Agent Test`
  - brands: `Basilur`, `Toras`
  - SKUs: `SKU001` (Basilur), `SKU002` (Toras)
  - Because the seed only has month 1, `max_luna_for_year(2026)` returns `1`. Period-filter tests therefore compare against **month 2** (empty) rather than month 1.
- Run tests with `pytest tests/ -q` from the project root. Run ETL/scripts from the project root too.

---

### Task 1: PPT layout primitive

**Files:**
- Modify: `app/exports/ppt_export.py`
- Test: `tests/test_ppt_primitive.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `fmt_ron(v) -> str` and `fmt_pct(v, suffix="%") -> str` — public aliases of the existing `_fmt_ron` / `_fmt_pct`, used by Task 3.
  - `_slide_kpi_tables(prs, title, subtitle, cards, tables) -> slide` where `cards` is `list[tuple[str, str]]` and `tables` is `list[dict]` with keys `title` (str), `headers` (list[str]), `rows` (list[dict]), `left` (float), `width` (float).
  - `_slide_chart_trend(prs, an, trend_by_year, title=None, subtitle=...)` — existing function, gains two optional keyword arguments.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ppt_primitive.py`:

```python
"""Unit tests for the shared PPT layout primitive."""
import sys
import os

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))

from exports import ppt_export  # noqa: E402


def _tables():
    return [
        {'title': 'Clienți', 'left': 0.3, 'width': 6.9,
         'headers': ['Client', 'VN'],
         'rows': [{'Client': 'A', 'VN': '1.000 RON'},
                  {'Client': 'B', 'VN': '2.000 RON'}]},
        {'title': 'Branduri', 'left': 7.4, 'width': 5.6,
         'headers': ['Brand', 'VN'],
         'rows': [{'Brand': 'Basilur', 'VN': '3.000 RON'}]},
    ]


def test_slide_kpi_tables_renders_cards_and_tables():
    prs = ppt_export._prs()
    slide = ppt_export._slide_kpi_tables(
        prs, 'Client: Test', '2026 · Ianuarie',
        [('Val. Netă', '1.000 RON'), ('Marjă Brută %', '20,0%')],
        _tables(),
    )
    graphic_frames = [s for s in slide.shapes if s.has_table]
    assert len(graphic_frames) == 2
    assert graphic_frames[0].table.cell(0, 0).text == 'Client'
    assert graphic_frames[0].table.cell(1, 0).text == 'A'
    texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
    assert 'Val. Netă' in texts
    assert '1.000 RON' in texts
    assert 'Clienți' in texts
    assert '2026 · Ianuarie' in texts


def test_slide_kpi_tables_skips_empty_tables():
    prs = ppt_export._prs()
    slide = ppt_export._slide_kpi_tables(
        prs, 'Brand: Gol', '2026', [('Val. Netă', '—')],
        [{'title': 'Clienți', 'left': 0.3, 'width': 6.9,
          'headers': ['Client'], 'rows': []}],
    )
    assert [s for s in slide.shapes if s.has_table] == []
    assert 'Clienți' not in [s.text_frame.text for s in slide.shapes if s.has_text_frame]


def test_slide_kpi_tables_caps_at_four_cards():
    prs = ppt_export._prs()
    slide = ppt_export._slide_kpi_tables(
        prs, 'X', 'Y',
        [('A', '1'), ('B', '2'), ('C', '3'), ('D', '4'), ('E', '5')], [])
    texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
    assert 'D' in texts
    assert 'E' not in texts


def test_public_formatters_are_exported():
    assert ppt_export.fmt_ron(1500) == '1.500 RON'
    assert ppt_export.fmt_ron(None) == '—'
    assert ppt_export.fmt_pct(12.34) == '12.3%'
    assert ppt_export.fmt_pct(None) == '—'


def test_trend_slide_accepts_custom_title():
    prs = ppt_export._prs()
    slide = ppt_export._slide_chart_trend(
        prs, 2026, {2026: [1] * 12}, title='Trend — Basilur')
    texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
    assert 'Trend — Basilur' in texts
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_ppt_primitive.py -v`
Expected: FAIL — `AttributeError: module 'exports.ppt_export' has no attribute '_slide_kpi_tables'`.

- [ ] **Step 3: Add the public formatter aliases**

In `app/exports/ppt_export.py`, rename the two formatter definitions and keep the old private names as aliases so no existing call site changes:

```python
def fmt_ron(v):
    if v is None:
        return "—"
    try:
        v = float(v)
        if abs(v) >= 1_000_000:
            return f"{v/1_000_000:.2f}M RON"
        return f"{int(v):,} RON".replace(",", ".")
    except Exception:
        return str(v)


def fmt_pct(v, suffix="%"):
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}{suffix}"
    except Exception:
        return str(v)


# Private aliases kept so the existing slide builders need no edits.
_fmt_ron = fmt_ron
_fmt_pct = fmt_pct
```

Delete the original `_fmt_ron` and `_fmt_pct` function definitions.

- [ ] **Step 4: Add the layout primitive**

Add below `_add_table` in `app/exports/ppt_export.py`:

```python
def _slide_kpi_tables(prs, title, subtitle, cards, tables):
    """Standard entity detail slide: a row of KPI cards, then one or two tables.

    cards  = [(label, value)] — at most 4, laid out left to right
    tables = [{'title', 'headers', 'rows', 'left', 'width'}] — empty rows are skipped
    """
    slide = _blank(prs)
    _header_bar(slide, title, subtitle)
    _footer(slide)

    for i, (label, value) in enumerate(cards[:4]):
        x = 0.3 + i * 3.15
        _add_rect(slide, x, 1.2, 3.0, 0.8, C_LGRAY)
        _add_text(slide, label, x + 0.1, 1.25, 2.8, 0.28,
                  font_size=8, color=C_ACCENT, bold=True)
        _add_text(slide, value, x + 0.1, 1.5, 2.8, 0.45,
                  font_size=13, bold=True, color=C_TEXT)

    for t in tables:
        rows = t.get('rows') or []
        if not rows:
            continue
        _add_text(slide, t['title'], t['left'], 2.15, t['width'], 0.3,
                  font_size=10, bold=True, color=C_DARK)
        _add_table(slide, rows, t['headers'], t['left'], 2.45, t['width'],
                   min(4.5, 0.4 * (len(rows) + 1)), font_size=8)

    return slide
```

- [ ] **Step 5: Make the trend slide reusable**

Change the signature and header call of `_slide_chart_trend`:

```python
def _slide_chart_trend(prs, an, trend_by_year, title=None,
                       subtitle="Val Netă RON pe lună"):
    """Bar chart cu trend lunar pe 3 ani (date YTD din monthly_trend)."""
    slide = _blank(prs)
    _header_bar(slide,
                title or f"Trend Lunar Vânzări — Comparativ {an-2}/{an-1}/{an}",
                subtitle)
    _footer(slide)
```

The rest of the function body is unchanged.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_ppt_primitive.py -v`
Expected: 5 passed.

- [ ] **Step 7: Verify nothing else broke**

Run: `pytest tests/ -q && ruff check .`
Expected: all pass, zero ruff errors.

- [ ] **Step 8: Commit**

```bash
git add app/exports/ppt_export.py tests/test_ppt_primitive.py
git commit -m "refactor(exports): add shared PPT KPI+tables slide primitive"
```

---

### Task 2: `agent_kpi` returns `marja_neta_pct`

The percentage is currently recomputed inline in two places with the same formula: `app/blueprints/analytics.py:112` and `app/blueprints/reports.py:168`. Move it into the query.

**Files:**
- Modify: `app/queries/analytics.py` (`agent_kpi`, lines 243-254)
- Modify: `app/blueprints/analytics.py` (lines 112-114)
- Modify: `app/blueprints/reports.py` (lines 168-170)
- Test: `tests/test_entity_exports.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `queries.agent_kpi(agent, an, max_luna=None, luna=None)` now includes key `marja_neta_pct` (float, `0` when `val_neta` is 0 or NULL).

- [ ] **Step 1: Write the failing test**

Create `tests/test_entity_exports.py` (later tasks append to this file):

```python
"""Exports for the entity detail pages: context, Excel round-trip, PPT, authz."""
import io

import openpyxl
import pytest
from pptx import Presentation

AN = 2026
AGENT = 'Agent Test'
CLIENT = 'C001'
BRAND = 'Basilur'
SKU = 'SKU001'
EMPTY_MONTH = 2  # the seed only has month 1, so month 2 yields no rows


def test_agent_kpi_exposes_marja_neta_pct(flask_app):
    import queries
    with flask_app.app_context():
        kpi = queries.agent_kpi(AGENT, AN)
    assert 'marja_neta_pct' in kpi
    expected = round((kpi['marja_neta'] or 0) * 100 / (kpi['val_neta'] or 1), 1)
    assert kpi['marja_neta_pct'] == pytest.approx(expected, abs=0.1)


def test_agent_kpi_marja_neta_pct_is_zero_without_sales(flask_app):
    import queries
    with flask_app.app_context():
        kpi = queries.agent_kpi('Agent Inexistent', AN)
    assert kpi['marja_neta_pct'] == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_entity_exports.py -v`
Expected: FAIL — `assert 'marja_neta_pct' in kpi`.

- [ ] **Step 3: Add the column to the query**

In `app/queries/analytics.py`, inside `agent_kpi`'s final `SELECT`, add one column after `marja_neta`. `COALESCE` to `0` so the value matches the old inline formula when `val_neta` is 0:

```sql
            ROUND(SUM(marja_bruta) - COALESCE((SELECT cost_conditii FROM cond_cost), 0), 0) AS marja_neta,
            COALESCE(ROUND((SUM(marja_bruta) - COALESCE((SELECT cost_conditii FROM cond_cost), 0))
                   * 100.0 / NULLIF(SUM(val_neta), 0), 1), 0) AS marja_neta_pct,
```

- [ ] **Step 4: Delete the two inline recomputations**

In `app/blueprints/analytics.py`, delete these three lines from `agent_detail`:

```python
    kpi['marja_neta_pct'] = round(
        (kpi.get('marja_neta') or 0) * 100 / (kpi.get('val_neta') or 1), 1
    )
```

In `app/blueprints/reports.py`, delete the same three lines from `export_ppt_agent`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_entity_exports.py tests/test_flask_routes.py -v`
Expected: PASS. `test_flask_routes.py` renders the agent page, which reads `kpi.marja_neta_pct` — it confirms the template still gets a number.

- [ ] **Step 6: Commit**

```bash
git add app/queries/analytics.py app/blueprints/analytics.py app/blueprints/reports.py tests/test_entity_exports.py
git commit -m "refactor(queries): compute agent marja_neta_pct in SQL, drop two inline copies"
```

---

### Task 3: Entity context builders

**Files:**
- Create: `app/exports/entities.py`
- Test: `tests/test_entity_exports.py` (append)

**Interfaces:**
- Consumes: `ppt_export.fmt_ron`, `ppt_export.fmt_pct` (Task 1); `queries.agent_kpi(...)['marja_neta_pct']` (Task 2).
- Produces: `entities.build_context(entity, ident, an, luna) -> dict | None`. Keys of the returned dict:
  - `nav` (str), `title` (str), `subtitle` (str), `filename_base` (str)
  - `cards` — `list[tuple[str, str]]`, at most 4
  - `tables` — `list[dict]` shaped for `_slide_kpi_tables`
  - `extra_tables` — `list[dict]` with `title`/`headers`/`rows`, rendered full-width on their own slide (only `agent` uses this)
  - `sheets` — `dict[str, list[dict]]` for `send_excel`
  - `trend` — `dict[int, list[float]]` (year → 12 monthly values)

**Deviation from spec §3.3, client entity — read this before implementing.** The spec lists the client cards as *Val. Netă / Marjă Brută % / Marjă Netă / Nr. Facturi*, matching today's deck. Today's deck is broken: `build_client_ppt` passes `dict(client_info(cod))` as the KPI source, and `client_info` returns no `marja_pct` and no `marja_neta`, so two of the four cards always render `"—"`. Its `val_neta_total` is also an all-time figure shown under a year heading. This task derives all four client cards from `client_products_full` for the selected period instead — same card labels, correct values, no new query. `Nr. Facturi` (all-time, from `client_info`) becomes `Nr. Produse` (period-scoped) so every card describes the same period.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_entity_exports.py`:

```python
# ── Context builders ─────────────────────────────────────────────────────────

ENTITY_IDENT = {
    'client': CLIENT,
    'agent': AGENT,
    'brand': BRAND,
    'produs': SKU,
}

ENTITY_NAV = {
    'client': 'clients',
    'agent': 'team',
    'brand': 'products',
    'produs': 'products',
}


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_build_context_shape(flask_app, entity):
    from exports import entities
    with flask_app.app_context():
        ctx = entities.build_context(entity, ENTITY_IDENT[entity], AN, None)
    assert ctx is not None
    assert ctx['nav'] == ENTITY_NAV[entity]
    assert ctx['title']
    assert ctx['filename_base']
    assert 1 <= len(ctx['cards']) <= 4
    assert all(isinstance(v, str) for _, v in ctx['cards'])
    assert len(ctx['sheets']) == 4
    for table in ctx['tables']:
        assert set(table) >= {'title', 'headers', 'rows', 'left', 'width'}


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_build_context_unknown_ident_returns_none(flask_app, entity):
    from exports import entities
    with flask_app.app_context():
        assert entities.build_context(entity, 'NU_EXISTA_XYZ', AN, None) is None


def test_build_context_unknown_entity_returns_none(flask_app):
    from exports import entities
    with flask_app.app_context():
        assert entities.build_context('nope', 'x', AN, None) is None


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_build_context_honours_luna(flask_app, entity):
    """Month 2 has no seeded rows, so its period sheets must come back empty
    while the unfiltered context has data."""
    from exports import entities
    with flask_app.app_context():
        full = entities.build_context(entity, ENTITY_IDENT[entity], AN, None)
        filtered = entities.build_context(entity, ENTITY_IDENT[entity], AN, EMPTY_MONTH)
    period_sheet = f'Clienți {AN}' if entity != 'client' else f'Produse {AN}'
    assert full['sheets'][period_sheet]
    assert filtered is None or not filtered['sheets'][period_sheet]


def test_period_label(flask_app):
    from exports import entities
    with flask_app.app_context():
        assert entities._period_label(2026, 7, None) == '2026 · Iulie'
        assert entities._period_label(2026, None, 7) == '2026 · Ian–Iul'
        assert entities._period_label(2026, None, 12) == '2026'
        assert entities._period_label(2026, None, None) == '2026'


def test_table_caption_reports_truncation(flask_app):
    from exports import entities
    rows = [{'x': i} for i in range(40)]
    table = entities._table('Clienți', 0.3, 6.9, rows, lambda r: {'X': str(r['x'])}, limit=15)
    assert table['title'] == 'Clienți — top 15 din 40'
    assert len(table['rows']) == 15
    assert table['headers'] == ['X']


def test_produs_context_aggregates_sku_variants(flask_app, monkeypatch):
    """sku_variants expansion must survive — the same article appears in
    tranzactii under several spellings and the page aggregates over all."""
    import queries
    from exports import entities
    seen = {}

    real_kpi = queries.product_kpi

    def spy(sku, an, **kw):
        seen['sku'] = sku
        return real_kpi(sku, an, **kw)

    monkeypatch.setattr(queries, 'product_kpi', spy)
    monkeypatch.setattr(queries, 'sku_variants', lambda s: [s, s + ' VARIANTA'])
    with flask_app.app_context():
        entities.build_context('produs', SKU, AN, None)
    assert seen['sku'] == [SKU, SKU + ' VARIANTA']
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_entity_exports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'exports.entities'`.

- [ ] **Step 3: Create the module**

Create `app/exports/entities.py`:

```python
"""Shared context builders for the entity detail exports.

Both the Excel route and the PPT route consume the context produced here, so
the two formats read the same rows for the same period and cannot drift apart.
"""
import queries
from exports.ppt_export import fmt_pct, fmt_ron

MONTHS_RO_FULL = [
    'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
    'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie',
]
MONTHS_RO_SHORT = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
                   'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _period_label(an, luna, max_luna):
    """Human-readable period, so a filtered export is never read as a full year."""
    if luna:
        return f"{an} · {MONTHS_RO_FULL[luna - 1]}"
    if max_luna and max_luna < 12:
        return f"{an} · Ian–{MONTHS_RO_SHORT[max_luna - 1]}"
    return str(an)


def _slug(text, maxlen):
    return (text or '').replace(' ', '_').replace('/', '_')[:maxlen]


def _table(title, left, width, rows, mapper, limit=15):
    """One deck table. States its own truncation so a top-N never reads as a total."""
    rows = rows or []
    mapped = [mapper(r) for r in rows[:limit]]
    caption = title if len(rows) <= limit else f"{title} — top {limit} din {len(rows)}"
    return {
        'title': caption,
        'left': left,
        'width': width,
        'headers': list(mapped[0].keys()) if mapped else [],
        'rows': mapped,
    }


def _trend(rows):
    """{year: [12 monthly val_neta]} for the trend chart."""
    out = {}
    for r in rows:
        luna = r.get('luna')
        if not luna:
            continue
        out.setdefault(r['an'], [0] * 12)[int(luna) - 1] = r.get('val_neta') or 0
    return out


def _pct(part, whole):
    return round((part or 0) * 100.0 / whole, 1) if whole else None


# ── Per-entity builders ──────────────────────────────────────────────────────

def _client(cod, an, luna, max_luna):
    info = queries.client_info(cod)
    if not info or not info.get('client'):
        return None
    products = queries.client_products_full(cod, an, luna=luna, max_luna=max_luna)
    yearly = queries.client_yearly_full(cod)
    name = info.get('client') or cod

    vn = sum((r.get('val_neta') or 0) for r in products)
    mb = sum((r.get('marja_bruta') or 0) for r in products)
    mn = sum((r.get('marja_neta') or 0) for r in products)

    return {
        'nav': 'clients',
        'title': f"Client: {name[:40]}",
        'filename_base': _slug(f"client_{name}", 36),
        'cards': [
            ("Val. Netă", fmt_ron(vn)),
            ("Marjă Brută %", fmt_pct(_pct(mb, vn))),
            ("Marjă Netă", fmt_ron(mn)),
            ("Nr. Produse", str(len(products))),
        ],
        'tables': [
            _table(f"Produse {an}", 0.3, 7.6, products, lambda r: {
                "Produs": (r.get('sku') or "—")[:28],
                "Brand": r.get('furnizor') or "—",
                "VN": fmt_ron(r.get('val_neta')),
                "MB%": fmt_pct(r.get('marja_bruta_pct')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
            }),
            _table("Evoluție anuală", 8.1, 4.9, yearly, lambda r: {
                "An": str(r.get('an') or ""),
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB%": fmt_pct(r.get('marja_bruta_pct')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
            }),
        ],
        'extra_tables': [],
        'sheets': {
            'Informații': [dict(info)],
            f'Produse {an}': products,
            'Brand Mix': queries.client_brand_mix(cod, an),
            'Evoluție Anuală': yearly,
        },
        'trend': _trend(queries.client_monthly_full(cod)),
    }


def _agent(name, an, luna, max_luna):
    kpi = queries.agent_kpi(name, an, luna=luna, max_luna=max_luna)
    if not kpi or not kpi.get('agent'):
        return None
    clients = queries.agent_clients_full(name, an, luna=luna, max_luna=max_luna)
    brands = queries.agent_brands_full(name, an, luna=luna, max_luna=max_luna)
    skus = queries.agent_skus_full(name, an, luna=luna, max_luna=max_luna)

    return {
        'nav': 'team',
        'title': f"Agent: {name}",
        'filename_base': _slug(f"agent_{name}_{an}", 40),
        'cards': [
            ("Val. Netă", fmt_ron(kpi.get('val_neta'))),
            ("Marjă Brută", f"{fmt_ron(kpi.get('marja_bruta'))} / {fmt_pct(kpi.get('marja_pct'))}"),
            ("Marjă Netă", f"{fmt_ron(kpi.get('marja_neta'))} / {fmt_pct(kpi.get('marja_neta_pct'))}"),
            ("Clienți Activi", str(kpi.get('clienti_activi') or 0)),
        ],
        'tables': [
            _table("Clienți", 0.3, 6.9, clients, lambda r: {
                "Client": (r.get('client') or "—")[:22],
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB%": fmt_pct(r.get('marja_bruta_pct')),
                "MN RON": fmt_ron(r.get('marja_neta')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
            }, limit=8),
            _table("Brand Mix", 7.4, 5.6, brands, lambda r: {
                "Brand": r.get('furnizor') or "—",
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB%": fmt_pct(r.get('marja_bruta_pct')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
            }, limit=8),
        ],
        'extra_tables': [
            _table(f"Top Produse {an}", 0.3, 12.7, skus, lambda r: {
                "Produs": (r.get('sku') or "—")[:30],
                "Brand": r.get('furnizor') or "—",
                "VN": fmt_ron(r.get('val_neta')),
                "MB%": fmt_pct(r.get('marja_bruta_pct')),
                "MN RON": fmt_ron(r.get('marja_neta')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
                "Clienți": str(r.get('nr_clienti') or 0),
            }),
        ],
        'sheets': {
            'KPI Agent': [dict(kpi)],
            f'Clienți {an}': clients,
            f'Top SKU {an}': skus,
            'Trend Lunar': queries.agent_monthly_full(name),
        },
        'trend': _trend(queries.agent_monthly_full(name)),
    }


def _brand(furnizor, an, luna, max_luna):
    kpi = queries.brand_kpi(furnizor, an, max_luna=max_luna, luna=luna)
    if not kpi or not kpi.get('val_neta'):
        return None
    clients = queries.brand_clients(furnizor, an, max_luna=max_luna, luna=luna)
    skus = queries.products_top_skus(an, furnizor=furnizor, limit=300,
                                     luna=luna, max_luna=max_luna)

    return {
        'nav': 'products',
        'title': f"Brand: {furnizor}",
        'filename_base': _slug(f"brand_{furnizor}_{an}", 40),
        'cards': [
            ("Val. Netă", fmt_ron(kpi.get('val_neta'))),
            ("Marjă Brută %", fmt_pct(kpi.get('marja_pct'))),
            ("Marjă Netă", f"{fmt_ron(kpi.get('marja_neta'))} / {fmt_pct(kpi.get('marja_neta_pct'))}"),
            ("Clienți / SKU", f"{kpi.get('nr_clienti') or 0} / {kpi.get('nr_sku') or 0}"),
        ],
        'tables': [
            _table("Top Clienți", 0.3, 6.9, clients, lambda r: {
                "Client": (r.get('client') or "—")[:22],
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB%": fmt_pct(r.get('marja_pct')),
                "Pond.%": fmt_pct(r.get('pondere')),
            }, limit=8),
            _table("Top SKU", 7.4, 5.6, skus, lambda r: {
                "Produs": (r.get('sku') or "—")[:24],
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB%": fmt_pct(r.get('marja_bruta_pct')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
            }, limit=8),
        ],
        'extra_tables': [],
        'sheets': {
            'KPI': [dict(kpi)],
            f'Clienți {an}': clients,
            f'Top SKU {an}': skus,
            'Trend Lunar': queries.brand_monthly_full(furnizor),
        },
        'trend': _trend(queries.brand_monthly_full(furnizor)),
    }


def _produs(sku, an, luna, max_luna):
    # The same physical article appears in tranzactii under several spellings;
    # the page aggregates over all of them and so must the export.
    variants = queries.sku_variants(sku)
    kpi = queries.product_kpi(variants, an, luna=luna, max_luna=max_luna)
    if not kpi or not kpi.get('sku'):
        return None
    clients = queries.product_clients(variants, an, luna=luna, max_luna=max_luna)
    yearly = queries.product_yearly(variants)
    monthly = queries.product_monthly(variants)

    return {
        'nav': 'products',
        'title': f"Produs: {sku[:38]}",
        'filename_base': _slug(f"produs_{sku}_{an}", 40),
        'cards': [
            ("Val. Netă", fmt_ron(kpi.get('val_neta'))),
            ("Marjă Brută %", fmt_pct(kpi.get('marja_bruta_pct'))),
            ("Marjă Netă", f"{fmt_ron(kpi.get('marja_neta'))} / {fmt_pct(kpi.get('marja_neta_pct'))}"),
            ("Clienți", str(kpi.get('nr_clienti') or 0)),
        ],
        'tables': [
            _table(f"Clienți {an}", 0.3, 7.6, clients, lambda r: {
                "Client": (r.get('client') or "—")[:26],
                "Agent": (r.get('agent') or "—")[:14],
                "Cant.": str(int(r.get('cantitate') or 0)),
                "VN": fmt_ron(r.get('val_neta')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
            }),
            _table("Evoluție anuală", 8.1, 4.9, yearly, lambda r: {
                "An": str(r.get('an') or ""),
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB%": fmt_pct(r.get('marja_bruta_pct')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
            }),
        ],
        'extra_tables': [],
        'sheets': {
            'KPI': [dict(kpi)],
            f'Clienți {an}': clients,
            'Evoluție Anuală': yearly,
            'Trend Lunar': monthly,
        },
        'trend': _trend(monthly),
    }


_BUILDERS = {
    'client': _client,
    'agent': _agent,
    'brand': _brand,
    'produs': _produs,
}

ENTITIES = tuple(_BUILDERS)


def build_context(entity, ident, an, luna=None):
    """Context for one entity detail export, or None when it does not resolve.

    The caller turns None into a 404. `luna` filters to a single month; when it
    is absent the period is year-to-date up to the last month that has data,
    exactly as the detail pages do.
    """
    builder = _BUILDERS.get(entity)
    if builder is None or not ident:
        return None
    max_luna = None if luna else queries.max_luna_for_year(an)
    ctx = builder(ident, an, luna, max_luna)
    if ctx is not None:
        ctx['subtitle'] = _period_label(an, luna, max_luna)
    return ctx
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_entity_exports.py -v`
Expected: all pass.

- [ ] **Step 5: Lint and full suite**

Run: `ruff check . && pytest tests/ -q`
Expected: zero errors, all pass.

- [ ] **Step 6: Commit**

```bash
git add app/exports/entities.py tests/test_entity_exports.py
git commit -m "feat(exports): add shared entity context builders for client/agent/brand/produs"
```

---

### Task 4: Entity PPT deck builder

**Files:**
- Modify: `app/exports/ppt_export.py`
- Test: `tests/test_entity_exports.py` (append)

**Interfaces:**
- Consumes: `_slide_kpi_tables`, `_slide_chart_trend(..., title=)` (Task 1); the context dict from `entities.build_context` (Task 3).
- Produces: `ppt_export.build_entity_ppt(ctx) -> BytesIO`. Slide count is `2 + len(ctx['extra_tables']) + (1 if ctx['trend'] else 0)`.
- Removes: `_slide_agent_detail`, `_slide_client_detail`, `build_agent_ppt`, `build_client_ppt`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_entity_exports.py`:

```python
# ── Deck builder ─────────────────────────────────────────────────────────────

EXPECTED_SLIDES = {'client': 3, 'agent': 4, 'brand': 3, 'produs': 3}


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_build_entity_ppt_slide_count(flask_app, entity):
    from exports import entities, ppt_export
    with flask_app.app_context():
        ctx = entities.build_context(entity, ENTITY_IDENT[entity], AN, None)
        buf = ppt_export.build_entity_ppt(ctx)
    prs = Presentation(buf)
    assert len(prs.slides) == EXPECTED_SLIDES[entity]


def test_build_entity_ppt_cover_shows_period(flask_app):
    from exports import entities, ppt_export
    with flask_app.app_context():
        ctx = entities.build_context('brand', BRAND, AN, 1)
        buf = ppt_export.build_entity_ppt(ctx)
    prs = Presentation(buf)
    texts = [s.text_frame.text for s in prs.slides[0].shapes if s.has_text_frame]
    assert '2026 · Ianuarie' in texts
    assert 'Brand: Basilur' in texts


def test_build_entity_ppt_without_trend_drops_the_chart_slide(flask_app):
    from exports import entities, ppt_export
    with flask_app.app_context():
        ctx = entities.build_context('brand', BRAND, AN, None)
    ctx['trend'] = {}
    buf = ppt_export.build_entity_ppt(ctx)
    assert len(Presentation(buf).slides) == 2


def test_old_named_builders_are_gone():
    from exports import ppt_export
    assert not hasattr(ppt_export, 'build_client_ppt')
    assert not hasattr(ppt_export, 'build_agent_ppt')
    assert not hasattr(ppt_export, '_slide_client_detail')
    assert not hasattr(ppt_export, '_slide_agent_detail')
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_entity_exports.py -k entity_ppt -v`
Expected: FAIL — `module 'exports.ppt_export' has no attribute 'build_entity_ppt'`.

- [ ] **Step 3: Add the deck builder**

Add to the "Public API" section of `app/exports/ppt_export.py`:

```python
def build_entity_ppt(ctx):
    """Deck for one entity detail page (client / agent / brand / produs).

    ctx comes from exports.entities.build_context — see that module for the
    key contract. Layout: cover, KPI+tables slide, one slide per extra table,
    then the monthly trend chart when there is trend data.
    """
    _check()
    prs = _prs()
    _slide_cover(prs, ctx['title'], "Raport detaliat", ctx['subtitle'])
    _slide_kpi_tables(prs, ctx['title'], ctx['subtitle'],
                      ctx['cards'], ctx['tables'])

    for table in ctx.get('extra_tables') or []:
        if not table['rows']:
            continue
        slide = _blank(prs)
        _header_bar(slide, f"{ctx['title']} — {table['title']}", ctx['subtitle'])
        _footer(slide)
        _add_table(slide, table['rows'], table['headers'],
                   table['left'], 1.2, table['width'], 5.8, font_size=8)

    trend = ctx.get('trend')
    if trend:
        an = max(trend)
        _slide_chart_trend(prs, an, trend,
                           title=f"{ctx['title']} — Trend Lunar")

    return _to_bytes(prs)
```

**Note on `extra_tables` and slide count:** the `agent` context always supplies one extra table, and the seeded agent has SKU rows, so the agent deck is 4 slides. If an entity's extra table is empty the slide is skipped — this is why `EXPECTED_SLIDES` is asserted against seeded data that is known non-empty.

- [ ] **Step 4: Delete the superseded builders**

Delete these four definitions from `app/exports/ppt_export.py`:

- `_slide_agent_detail` (lines ~320-363)
- `_slide_client_detail` (lines ~366-409)
- `build_agent_ppt` (lines ~558-580)
- `build_client_ppt` (lines ~583-588)

Leave `_slide_agents_table`, `_slide_top_clients`, `_slide_risk`, `build_dashboard_ppt`, `build_profitabilitate_ppt` and `build_basilur_ppt` untouched — they serve the overview decks.

`reports.py` still calls `build_agent_ppt` / `build_client_ppt` at this point, so the app is temporarily broken. Task 5 fixes it; do not commit these two tasks separately.

- [ ] **Step 5: Run the deck tests**

Run: `pytest tests/test_entity_exports.py -k "entity_ppt or old_named" -v`
Expected: PASS. The full suite will still fail on the route tests until Task 5 — that is expected here.

---

### Task 5: PPT dispatcher route, nav registry, template links

Completes Task 4. Both tasks land in one commit.

**Files:**
- Modify: `app/blueprints/reports.py` (replace lines 131-202)
- Modify: `app/nav_registry.py` (NavItem tuples, `UNGATED_ENDPOINTS`)
- Modify: `app/templates/dashboard.html:10`, `app/templates/agent.html:30`, `app/templates/client.html:46`, `app/templates/profitabilitate.html:18`
- Test: `tests/test_entity_exports.py` (append)

**Interfaces:**
- Consumes: `entities.build_context` (Task 3), `ppt_export.build_entity_ppt` (Task 4).
- Produces: endpoint `reports.export_ppt`, URL `/export/ppt/<entity>`. Entities: `dashboard`, `profitabilitate` (no ident), `client` (`cod_client`), `agent` (`name`), `brand` (`furnizor`), `produs` (`sku`). All accept `an` and `luna`.
- Removes: endpoints `reports.export_ppt_dashboard`, `reports.export_ppt_agent`, `reports.export_ppt_client`, `reports.export_ppt_profitabilitate`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_entity_exports.py`:

```python
# ── PPT route ────────────────────────────────────────────────────────────────

PPT_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'

PPT_QUERY = {
    'client': f'cod_client={CLIENT}',
    'agent': 'name=Agent+Test',
    'brand': f'furnizor={BRAND}',
    'produs': f'sku={SKU}',
}


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_ppt_route_returns_openable_deck(client, entity):
    rv = client.get(f'/export/ppt/{entity}?{PPT_QUERY[entity]}&an={AN}')
    assert rv.status_code == 200
    assert rv.mimetype == PPT_MIME
    assert rv.data
    prs = Presentation(io.BytesIO(rv.data))
    assert len(prs.slides) == EXPECTED_SLIDES[entity]


@pytest.mark.parametrize('entity', ['dashboard', 'profitabilitate'])
def test_ppt_route_still_serves_overview_decks(client, entity):
    rv = client.get(f'/export/ppt/{entity}?an={AN}')
    assert rv.status_code == 200
    assert rv.mimetype == PPT_MIME
    assert len(Presentation(io.BytesIO(rv.data)).slides) >= 2


def test_ppt_route_unknown_entity_is_404(client):
    assert client.get('/export/ppt/nope').status_code == 404


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_ppt_route_missing_ident_is_404(client, entity):
    assert client.get(f'/export/ppt/{entity}?an={AN}').status_code == 404


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_ppt_route_unknown_ident_is_404(client, entity):
    param = PPT_QUERY[entity].split('=')[0]
    rv = client.get(f'/export/ppt/{entity}?{param}=NU_EXISTA_XYZ&an={AN}')
    assert rv.status_code == 404


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs', 'dashboard'])
def test_ppt_route_denies_role_without_nav_access(client, monkeypatch, entity):
    import authz
    monkeypatch.setattr(authz, 'can_access_nav', lambda role, key: False)
    query = PPT_QUERY.get(entity, '')
    rv = client.get(f'/export/ppt/{entity}?{query}&an={AN}')
    assert rv.status_code == 403


def test_old_ppt_endpoints_are_gone(flask_app):
    endpoints = {r.endpoint for r in flask_app.url_map.iter_rules()}
    assert 'reports.export_ppt' in endpoints
    for old in ('reports.export_ppt_client', 'reports.export_ppt_agent',
                'reports.export_ppt_dashboard', 'reports.export_ppt_profitabilitate'):
        assert old not in endpoints


def test_ppt_route_is_allowlisted_not_orphaned():
    import nav_registry as nr
    assert 'reports.export_ppt' in nr.UNGATED_ENDPOINTS
    registered = {ep for item in nr.NAV_REGISTRY for ep in item.endpoints}
    assert 'reports.export_ppt_client' not in registered
    assert 'reports.export_ppt_agent' not in registered
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_entity_exports.py -k ppt_route -v`
Expected: FAIL with 404s — `/export/ppt/<entity>` is not routed yet.

- [ ] **Step 3: Replace the four PPT routes with the dispatcher**

In `app/blueprints/reports.py`, add the import next to the existing export imports:

```python
from exports import entities, ppt_export
```

(replacing the current `from exports import ppt_export`).

Then replace the whole block from `@reports_bp.route('/export/ppt/dashboard')` through the end of `export_ppt_profitabilitate` with:

```python
# (nav key, request arg carrying the entity id — None for overview decks)
_PPT_ENTITIES = {
    'dashboard':       ('dashboard', None),
    'profitabilitate': ('profitabilitate', None),
    'client':          ('clients', 'cod_client'),
    'agent':           ('team', 'name'),
    'brand':           ('products', 'furnizor'),
    'produs':          ('products', 'sku'),
}


def _dashboard_ppt(an):
    kpis = {r['an']: r for r in queries.kpi_cards()}
    cy = kpis.get(an, {})
    py = kpis.get(an - 1, {})
    delta_vn = _delta_pct(cy.get('val_neta', 0), py.get('val_neta', 0))
    delta_mb = _delta_pct(cy.get('marja_bruta', 0), py.get('marja_bruta', 0))
    delta_mn = _delta_pct(cy.get('marja_neta', 0), py.get('marja_neta', 0))
    delta_mpct = round((cy.get('marja_pct', 0) or 0) - (py.get('marja_pct', 0) or 0), 1)
    buf = ppt_export.build_dashboard_ppt(
        an, cy, py, delta_vn, delta_mb, delta_mn, delta_mpct,
        queries.profitabilitate_agenti(an),
        queries.profitabilitate_clienti(an, limit=15),
        queries.risk_kaufland(an),
        queries.risk_agent(an, 'DRAGNEA BOGDAN'),
        queries.churn_clients(60),
        trend_by_year=_build_trend_series(queries.monthly_trend()),
        brands_data=queries.brand_mix(an),
        channels_data=queries.channel_mix(an),
    )
    return buf, f'dashboard_{an}'


def _profitabilitate_ppt(an):
    buf = ppt_export.build_profitabilitate_ppt(
        an,
        queries.profitabilitate_agenti(an),
        queries.profitabilitate_clienti(an),
        queries.profitabilitate_produse(an),
    )
    return buf, f'profitabilitate_{an}'


_OVERVIEW_PPT = {
    'dashboard': _dashboard_ppt,
    'profitabilitate': _profitabilitate_ppt,
}


@reports_bp.route('/export/ppt/<entity>')
def export_ppt(entity):
    """Generic multi-feature PPT export — gated per-entity here, which is why
    this endpoint is allow-listed in nav_registry.UNGATED_ENDPOINTS."""
    spec = _PPT_ENTITIES.get(entity)
    if spec is None:
        abort(404)
    nav, param = spec
    if not authz.can_access_nav(current_user.role, nav):
        abort(403)

    an = int(request.args.get('an', datetime.date.today().year))

    if param is None:
        buf, base = _OVERVIEW_PPT[entity](an)
        return ppt_export.send_ppt(buf, ppt_export.timestamped_filename(base))

    ident = request.args.get(param, '').strip()
    luna = request.args.get('luna', type=int)
    ctx = entities.build_context(entity, ident, an, luna) if ident else None
    if ctx is None:
        abort(404)
    buf = ppt_export.build_entity_ppt(ctx)
    return ppt_export.send_ppt(
        buf, ppt_export.timestamped_filename(ctx['filename_base']))
```

- [ ] **Step 4: Update the nav registry**

In `app/nav_registry.py`, drop the four PPT endpoints from the NavItem tuples:

```python
    NavItem("dashboard", "Dashboard", "speedometer2", "Analiză",
            "analytics.dashboard",
            endpoints=("analytics.dashboard",)),
    NavItem("team", "Echipă", "people-fill", "Analiză",
            "analytics.team",
            endpoints=("analytics.team", "analytics.agent_detail")),
    NavItem("clients", "Clienți", "building", "Analiză",
            "analytics.clients",
            endpoints=("analytics.clients", "analytics.client_detail")),
```

and

```python
    NavItem("profitabilitate", "Profitabilitate", "graph-up-arrow", "Analiză",
            "reports.profitabilitate",
            endpoints=("reports.profitabilitate",)),
```

Then add the dispatcher to the allow-list, next to the existing `reports.export_excel` entry:

```python
    # generic multi-feature export — gated per-report inside the handler (see reports.export_excel)
    "reports.export_excel",
    # generic multi-entity PPT export — gated per-entity inside the handler
    "reports.export_ppt",
```

- [ ] **Step 5: Update the four templates**

`app/templates/dashboard.html:10`:

```jinja
    <a href="{{ url_for('reports.export_ppt', entity='dashboard', an=an) }}"
```

`app/templates/profitabilitate.html:18`:

```jinja
    <a href="{{ url_for('reports.export_ppt', entity='profitabilitate', an=an) }}"
```

`app/templates/agent.html:30`:

```jinja
    <a href="{{ url_for('reports.export_ppt', entity='agent', name=agent, an=an, luna=luna) }}"
```

`app/templates/client.html:46`:

```jinja
    <a href="{{ url_for('reports.export_ppt', entity='client', cod_client=info.cod_client, an=an, luna=luna) }}"
```

Leave the surrounding `class`, `title` and `<i>` markup on each link exactly as it is.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/ -q`
Expected: all pass, including `test_endpoint_coverage.py`, `test_nav_registry.py` and `test_nav_render.py`.

- [ ] **Step 7: Lint**

Run: `ruff check .`
Expected: zero errors.

- [ ] **Step 8: Commit (covers Tasks 4 and 5)**

```bash
git add app/exports/ppt_export.py app/blueprints/reports.py app/nav_registry.py app/templates/ tests/test_entity_exports.py
git commit -m "feat(exports): single /export/ppt/<entity> dispatcher, add brand and produs decks"
```

---

### Task 6: Excel entity branches delegate to the shared context

**Files:**
- Modify: `app/blueprints/reports.py` (`_EXPORT_NAV_KEY`, `export_excel` — the `agent`, `client`, `produs` branches; add `brand`)
- Test: `tests/test_entity_exports.py` (append)

**Interfaces:**
- Consumes: `entities.build_context` (Task 3).
- Produces: `/export/brand?furnizor=<name>&an=<year>&luna=<month>` returns an xlsx. The `agent`, `client` and `produs` Excel branches now honour `luna`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_entity_exports.py`:

```python
# ── Excel route ──────────────────────────────────────────────────────────────

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

XLSX_QUERY = {
    'client': f'cod_client={CLIENT}',
    'agent': 'name=Agent+Test',
    'brand': f'furnizor={BRAND}',
    'produs': f'sku={SKU}',
}

EXPECTED_SHEETS = {
    'client': ['Informații', f'Produse {AN}', 'Brand Mix', 'Evoluție Anuală'],
    'agent': ['KPI Agent', f'Clienți {AN}', f'Top SKU {AN}', 'Trend Lunar'],
    'brand': ['KPI', f'Clienți {AN}', f'Top SKU {AN}', 'Trend Lunar'],
    'produs': ['KPI', f'Clienți {AN}', 'Evoluție Anuală', 'Trend Lunar'],
}


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_excel_route_returns_openable_workbook(client, entity):
    rv = client.get(f'/export/{entity}?{XLSX_QUERY[entity]}&an={AN}')
    assert rv.status_code == 200
    assert rv.mimetype == XLSX_MIME
    wb = openpyxl.load_workbook(io.BytesIO(rv.data))
    assert wb.sheetnames == EXPECTED_SHEETS[entity]


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_excel_route_honours_luna(client, entity):
    """Month 2 has no seeded rows. The period sheet must be empty, proving the
    filter reaches the query instead of the export silently returning the year."""
    rv = client.get(
        f'/export/{entity}?{XLSX_QUERY[entity]}&an={AN}&luna={EMPTY_MONTH}')
    if rv.status_code == 404:
        return  # entity does not resolve in an empty period — also correct
    wb = openpyxl.load_workbook(io.BytesIO(rv.data))
    sheet_name = f'Produse {AN}' if entity == 'client' else f'Clienți {AN}'
    ws = wb[sheet_name]
    assert ws['A1'].value == 'Nu există date pentru acest raport.'


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_excel_route_unknown_ident_is_404(client, entity):
    param = XLSX_QUERY[entity].split('=')[0]
    rv = client.get(f'/export/{entity}?{param}=NU_EXISTA_XYZ&an={AN}')
    assert rv.status_code == 404


def test_excel_brand_is_gated_on_products_nav(client, monkeypatch):
    import authz
    monkeypatch.setattr(authz, 'can_access_nav', lambda role, key: False)
    rv = client.get(f'/export/brand?furnizor={BRAND}&an={AN}')
    assert rv.status_code == 403
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_entity_exports.py -k excel_route -v`
Expected: FAIL — `/export/brand` returns 404 (no `brand` branch), and the `luna` tests fail because the period sheets still contain data.

- [ ] **Step 3: Add `brand` to the nav-key map**

In `app/blueprints/reports.py`, add one entry to `_EXPORT_NAV_KEY`:

```python
    "products": "products",
    "produs": "products",
    "brand": "products",
```

- [ ] **Step 4: Replace the four entity branches**

In `export_excel`, delete the existing `agent`, `client` and `produs` branches and put this single block in their place (keep it where the `agent` branch is today, so the eight non-entity branches stay in their current order):

```python
    if report in entities.ENTITIES:
        param = _PPT_ENTITIES[report][1]
        ident = request.args.get(param, '').strip()
        luna = request.args.get('luna', type=int)
        ctx = entities.build_context(report, ident, an, luna) if ident else None
        if ctx is None:
            abort(404)
        return send_excel(ctx['sheets'],
                          timestamped_filename(ctx['filename_base']))
```

`_PPT_ENTITIES` is defined in Task 5 and carries the request-argument name for each entity; reusing it keeps the Excel and PPT routes reading the same parameter (`cod_client`, `name`, `furnizor`, `sku`).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_entity_exports.py -v`
Expected: all pass.

- [ ] **Step 6: Full suite and lint**

Run: `pytest tests/ -q && ruff check .`
Expected: all pass, zero errors.

- [ ] **Step 7: Commit**

```bash
git add app/blueprints/reports.py tests/test_entity_exports.py
git commit -m "feat(exports): brand Excel export, entity Excel branches honour the month filter"
```

---

### Task 7: Export buttons on the brand and produs pages

**Files:**
- Modify: `app/templates/brand.html`
- Modify: `app/templates/produs.html`
- Test: `tests/test_entity_exports.py` (append)

**Interfaces:**
- Consumes: `reports.export_ppt` (Task 5), the `brand` Excel branch (Task 6).
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_entity_exports.py`:

```python
# ── Page buttons ─────────────────────────────────────────────────────────────

def test_brand_page_offers_both_exports(client):
    html = client.get(f'/brand/{BRAND}?an={AN}').get_data(as_text=True)
    assert f'/export/brand?furnizor={BRAND}' in html or '/export/brand?' in html
    assert '/export/ppt/brand?' in html


def test_produs_page_offers_ppt_export(client):
    html = client.get(f'/produs/{SKU}?an={AN}').get_data(as_text=True)
    assert '/export/produs?' in html
    assert '/export/ppt/produs?' in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_entity_exports.py -k page_offers -v`
Expected: FAIL — neither page renders an export link.

- [ ] **Step 3: Add the button pair to `brand.html`**

`brand.html:12-16` already has the flex header wrapper; it just has no action area. Replace those five lines with:

```jinja
<div class="d-flex justify-content-between align-items-center mb-4">
  <h4 class="mb-0 fw-bold">
    <i class="bi bi-award-fill text-warning me-1"></i>{{ furnizor }}
  </h4>
  <div class="d-flex gap-2 align-items-center">
    <a href="{{ url_for('reports.export_excel', report='brand', furnizor=furnizor, an=an, luna=luna) }}"
       class="btn btn-sm btn-outline-success" title="Export Excel">
      <i class="bi bi-file-earmark-excel"></i> Excel
    </a>
    <a href="{{ url_for('reports.export_ppt', entity='brand', furnizor=furnizor, an=an, luna=luna) }}"
       class="btn btn-sm btn-outline-danger" title="Export PPT">
      <i class="bi bi-file-earmark-slides"></i> PPT
    </a>
  </div>
</div>
```

This mirrors `client.html:36-50`.

- [ ] **Step 4: Add the PPT button to `produs.html`**

`produs.html:29-34` already has the action div with the Excel link. Add the PPT link after it, inside the same `<div class="d-flex gap-2 align-items-center">`:

```jinja
    <a href="{{ url_for('reports.export_ppt', entity='produs', sku=sku, an=an, luna=luna) }}"
       class="btn btn-sm btn-outline-danger" title="Export PPT">
      <i class="bi bi-file-earmark-slides"></i> PPT
    </a>
```

While here, add `luna=luna` to the existing Excel link on line 30 so it matches:

```jinja
    <a href="{{ url_for('reports.export_excel', report='produs', sku=sku, an=an, luna=luna) }}"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_entity_exports.py -k page_offers -v`
Expected: PASS.

- [ ] **Step 6: Full suite and lint**

Run: `pytest tests/ -q && ruff check .`
Expected: all pass, zero errors.

- [ ] **Step 7: Manual check in the running app**

Start the app and visit `/brand/Basilur` and `/produs/SKU001`. Confirm both buttons render side by side and each download opens in Excel / PowerPoint without a repair prompt. Then set a month filter on each page and confirm the downloaded file's period matches the screen and the deck cover reads e.g. `2026 · Ianuarie`.

- [ ] **Step 8: Commit**

```bash
git add app/templates/brand.html app/templates/produs.html tests/test_entity_exports.py
git commit -m "feat(ui): export buttons on the brand page, PPT button on the produs page"
```

---

### Task 8: Documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/BACKLOG.md`
- Modify: `context/STATUS.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Add the `[Unreleased]` changelog entry**

Under `## [Unreleased]` in `CHANGELOG.md`, following the file's existing Keep-a-Changelog headings:

```markdown
### Added
- Export Excel și PPT pe pagina de brand; export PPT pe pagina de produs.
- Slide de trend lunar în deck-urile de client, agent, brand și produs.

### Changed
- Cele patru rute PPT numite au fost înlocuite cu un singur dispatcher
  `/export/ppt/<entity>`, protejat per-entitate în handler (ca `export_excel`).
- Exporturile de entitate (client, agent, brand, produs) respectă acum filtrul
  de lună: fișierul descărcat acoperă aceeași perioadă ca ecranul. Perioada
  este scrisă explicit pe copertă și în antetul slide-ului.
- Tabelele din deck-uri își declară trunchierea („Top 15 din 340").

### Fixed
- Cardurile „Marjă Brută" și „Marjă Netă" din deck-ul de client afișau „—":
  sursa lor (`client_info`) nu conține aceste câmpuri. Sunt calculate acum din
  produsele perioadei selectate.
```

- [ ] **Step 2: Log the two deferred items in `docs/BACKLOG.md`**

Add under the appropriate section, matching the file's existing item format:

```markdown
- **Etichete româneşti pentru coloanele din exporturile Excel.** Anteturile sunt
  numele brute din DB (`val_neta`, `marja_neta_pct`) în 9 din 10 rapoarte; doar
  forecast le mapează. Soluţie: un dicţionar `COLUMN_LABELS` partajat în
  `app/exports/excel_export.py`, aplicat în `_write_sheet`.
- **Registru pentru lanţul `if` din `export_excel`.** Cele 8 rapoarte non-entitate
  primesc filtre foarte diferite; un registru ar avea nevoie de un extractor de
  parametri per intrare. De reevaluat dacă se mai adaugă rapoarte.
```

- [ ] **Step 3: Update `context/STATUS.md`**

Update the "Next immediate step" section to reflect that the entity export work is delivered. Keep delivery detail in `CHANGELOG.md`, not here — `STATUS.md` holds current state only.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md docs/BACKLOG.md context/STATUS.md
git commit -m "docs: record entity export standardisation, log deferred export items"
```

---

## Verification

Before declaring the work complete, run and confirm the output of all three:

```bash
ruff check .
pytest tests/ -q
git log --oneline -6
```

Expected: zero ruff errors; every test passing; six commits matching the tasks above.

Then confirm by hand in the running app:

1. `/brand/<any brand>` — Excel and PPT buttons present, both files open cleanly.
2. `/produs/<any sku>` — PPT button present next to Excel.
3. `/client/<any code>` and `/agent/<any name>` — existing buttons still work, decks now carry a trend slide, and the client deck's margin cards show numbers rather than `—`.
4. `/` and `/profitabilitate` — PPT buttons still work through the new dispatcher URL.
5. On any of the four detail pages, set a month filter and confirm the exported file covers that month and the deck cover states it.
