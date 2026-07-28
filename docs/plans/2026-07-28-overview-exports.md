# Overview Exports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the `team`, `clients`, `products` and `raportare-basilur` pages the same Excel + PPT export standard the entity detail pages already have, driven by one shared context per report.

**Architecture:** Extract the primitives currently private to `app/exports/entities.py` into a new `app/exports/context.py`, then add a sibling `app/exports/overviews.py` holding four filter-keyed builders that emit the same context dict. Both dispatchers (`/export/<report>`, `/export/ppt/<entity>`) consult `overviews.REPORTS` first and fall through to the existing entity path.

**Tech Stack:** Flask, SQLite, `openpyxl` (Excel), `python-pptx` (decks), pytest.

**Spec:** `docs/specs/2026-07-28-overview-exports-design.md`

## Global Constraints

- Formats are **Excel + PPT only**. No PDF engine is introduced.
- All Python must pass `ruff check .` with zero errors. Forbidden: `E401`, `E402`, `E701`, `E702`, `E722`, `E741`, `F401`, `F841`.
- Developer-facing text (code, comments, commit messages) in **English**; user-facing UI strings in **Romanian** — except `raportare-basilur`, whose export content stays **English + USD** because it is the supplier-facing report.
- Romanian strings in `.py` files: read `docs/TECHNICAL.md` §Encoding before editing any `.py` containing diacritics.
- `tests/test_entity_exports.py` must keep passing **unmodified** — it is the regression guard for the `context.py` extraction.
- Modules under `app/` import each other by top-level name (`import queries`, `from exports.context import ...`) because `app/` is on `sys.path`.
- Overview exports **never 404 on an empty result** — an empty filter match is a valid answer and yields an empty sheet. They 404 only on an unknown report or an out-of-range `luna`.
- Excel sheets are never truncated; deck tables truncate and declare it in their caption.
- Run tests from the project root: `python -m pytest tests/ -q`.

---

### Task 1: Extract shared context primitives

**Files:**
- Create: `app/exports/context.py`
- Modify: `app/exports/entities.py:1-80`, `app/exports/entities.py:187-204`
- Test: `tests/test_entity_exports.py` (must pass unmodified)

**Interfaces:**
- Consumes: nothing.
- Produces: `exports.context` exposing `MONTHS_RO_FULL: list[str]`, `MONTHS_RO_SHORT: list[str]`, `SHEET_ROW_LIMIT: int`, `period_label(an, luna, max_luna) -> str`, `slug(text, maxlen) -> str`, `slug_with_year(prefix, ident, an, maxlen) -> str`, `table(title, left, width, rows, mapper, limit=15) -> dict`, `trend(rows) -> dict[int, list[float]]`, `pct(part, whole) -> float | None`.

- [ ] **Step 1: Run the entity export tests to record the green baseline**

Run: `python -m pytest tests/test_entity_exports.py -q`
Expected: PASS (all tests). Note the count — it must be identical after the refactor.

- [ ] **Step 2: Create `app/exports/context.py`**

Move the bodies verbatim out of `entities.py`; only the names lose their leading underscore.

```python
"""Primitives shared by the entity and overview export context builders.

`exports.entities` resolves one identifier; `exports.overviews` resolves a set
of filters. Both emit the same context dict, so `ppt_export.build_entity_ppt`
and `excel_export.send_excel` consume either without a branch.
"""

MONTHS_RO_FULL = [
    'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
    'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie',
]
MONTHS_RO_SHORT = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
                   'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# The workbook sheet is the full-data artifact (unlike the deck table, which
# declares its own top-N truncation), so its underlying queries must pull
# effectively all rows. Several of them bind `LIMIT :limit` and SQLite raises
# on a NULL bind there, so "unlimited" is expressed as a number comfortably
# above any real row count.
SHEET_ROW_LIMIT = 100_000


def period_label(an, luna, max_luna):
    """Human-readable period, so a filtered export is never read as a full year."""
    if luna:
        return f"{an} · {MONTHS_RO_FULL[luna - 1]}"
    if max_luna and max_luna < 12:
        return f"{an} · Ian–{MONTHS_RO_SHORT[max_luna - 1]}"
    return str(an)


def slug(text, maxlen):
    return (text or '').replace(' ', '_').replace('/', '_')[:maxlen]


def slug_with_year(prefix, ident, an, maxlen):
    """Slug that always keeps the trailing `_<year>` — the identifier is
    truncated instead of the whole composed string, so a long ident never
    eats the year suffix (pre-branch behaviour)."""
    suffix = f"_{an}"
    ident = (ident or '').replace(' ', '_').replace('/', '_')
    budget = max(maxlen - len(prefix) - 1 - len(suffix), 0)
    return f"{prefix}_{ident[:budget]}{suffix}"


def table(title, left, width, rows, mapper, limit=15):
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


def trend(rows):
    """{year: [12 monthly val_neta]} for the trend chart."""
    out = {}
    for r in rows:
        luna = r.get('luna')
        if not luna:
            continue
        out.setdefault(r['an'], [0] * 12)[int(luna) - 1] = r.get('val_neta') or 0
    return out


def pct(part, whole):
    return round((part or 0) * 100.0 / whole, 1) if whole else None
```

- [ ] **Step 3: Rewrite the head of `app/exports/entities.py`**

Delete lines 9–79 (the constants and the seven helpers) and lines 187–192 (the
`_SHEET_ROW_LIMIT` block), then replace the import header. The aliases keep
`entities._period_label`, `entities._slug_with_year` and `entities._table`
bound, which is what `tests/test_entity_exports.py` asserts against.

```python
"""Shared context builders for the entity detail exports.

Both the Excel route and the PPT route consume the context produced here, so
the two formats read the same rows for the same period and cannot drift apart.
"""
import queries
from exports.context import SHEET_ROW_LIMIT
from exports.context import pct as _pct
from exports.context import period_label as _period_label
from exports.context import slug as _slug
from exports.context import slug_with_year as _slug_with_year
from exports.context import table as _table
from exports.context import trend as _trend
from exports.ppt_export import fmt_pct, fmt_ron
```

Leave `_brand_mix` where it is — it is entity-specific, not shared.

- [ ] **Step 4: Repoint the two `_SHEET_ROW_LIMIT` uses in `_brand`**

```python
    clients = queries.brand_clients(furnizor, an, max_luna=max_luna, luna=luna,
                                     limit=SHEET_ROW_LIMIT)
    skus = queries.products_top_skus(an, furnizor=furnizor, limit=SHEET_ROW_LIMIT,
                                     luna=luna, max_luna=max_luna)
```

- [ ] **Step 5: Run the entity export tests**

Run: `python -m pytest tests/test_entity_exports.py -q`
Expected: PASS, same test count as Step 1. A failure here means an alias is missing.

- [ ] **Step 6: Lint**

Run: `ruff check .`
Expected: no errors. `F401` here would mean an alias was imported but never used — delete that one line rather than suppressing.

- [ ] **Step 7: Commit**

```bash
git add app/exports/context.py app/exports/entities.py
git commit -m "refactor(exports): extract shared context primitives into exports.context"
```

---

### Task 2: Overview builders for `team` and `clients`

**Files:**
- Create: `app/exports/overviews.py`
- Test: `tests/test_overview_exports.py` (create)

**Interfaces:**
- Consumes: `exports.context.{table, pct, period_label, SHEET_ROW_LIMIT}`, `exports.ppt_export.{fmt_ron, fmt_pct}`, `queries.{team_table, clients_list, max_luna_for_year}`.
- Produces: `overviews.build_context(report, an, luna=None, filters=None) -> dict | None` and `overviews.REPORTS: tuple[str, ...]`. The dict carries `nav, title, subtitle, filename_base, cards, tables, extra_tables, sheets, trend`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_overview_exports.py`:

```python
"""Exports for the list/report pages: context, filters, period, Excel, PPT, authz."""

import io

import openpyxl
import pytest
from pptx import Presentation

AN = 2026
EMPTY_MONTH = 2  # the seed only has month 1, so month 2 yields no rows

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PPT_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'


def _rows(sheet):
    """Sheets are either a plain row list or {'rows', 'headers'} (basilur)."""
    return sheet['rows'] if isinstance(sheet, dict) else sheet


def test_team_context_shape(flask_app):
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('team', AN, None, {})
    assert ctx['nav'] == 'team'
    assert ctx['filename_base'] == f'echipa_{AN}'
    # The seed only has January, so max_luna is 1 and period_label renders a
    # one-month year-to-date range.
    assert ctx['subtitle'] == '2026 · Ian–Ian'
    assert list(ctx['sheets']) == [f'Echipa {AN}', f'Echipa {AN - 1}']
    # Seed (tests/conftest.py): one agent, val_neta 500+400=900,
    # marja_bruta 200+150=350, no conditii rows so marja neta == marja bruta.
    assert ctx['cards'] == [
        ("Val. Netă", "900 RON"),
        ("Marjă Brută", "350 RON / 38.9%"),
        ("Marjă Netă", "350 RON / 38.9%"),
        ("Nr. Agenți", "1"),
    ]


def test_clients_context_shape(flask_app):
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('clients', AN, None, {})
    assert ctx['nav'] == 'clients'
    assert ctx['filename_base'] == f'clienti_{AN}'
    assert list(ctx['sheets']) == [f'Clienți {AN}']
    assert len(_rows(ctx['sheets'][f'Clienți {AN}'])) == 2


def test_clients_context_honours_brand_filter(flask_app):
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('clients', AN, None, {'brand': 'Basilur'})
    codes = [r['cod_client'] for r in _rows(ctx['sheets'][f'Clienți {AN}'])]
    assert codes == ['C001']


@pytest.mark.parametrize('report', ['team', 'clients'])
def test_context_honours_luna(flask_app, report):
    """Month 2 has no seeded rows, so its period sheet must come back empty
    while the unfiltered context has data. /export/team used to drop luna."""
    from exports import overviews
    with flask_app.app_context():
        full = overviews.build_context(report, AN, None, {})
        empty = overviews.build_context(report, AN, EMPTY_MONTH, {})
    first = list(full['sheets'])[0]
    assert _rows(full['sheets'][first])
    assert not _rows(empty['sheets'][first])
    assert empty['subtitle'] == '2026 · Februarie'


@pytest.mark.parametrize('report', ['team', 'clients'])
@pytest.mark.parametrize('luna', [13, -1])
def test_context_rejects_out_of_range_luna(flask_app, report, luna):
    from exports import overviews
    with flask_app.app_context():
        assert overviews.build_context(report, AN, luna, {}) is None


def test_context_unknown_report_returns_none(flask_app):
    from exports import overviews
    with flask_app.app_context():
        assert overviews.build_context('nope', AN, None, {}) is None


@pytest.mark.parametrize('report', ['team', 'clients'])
def test_context_luna_zero_is_year_to_date(flask_app, report):
    from exports import overviews
    with flask_app.app_context():
        zero = overviews.build_context(report, AN, 0, {})
        none = overviews.build_context(report, AN, None, {})
    assert zero['subtitle'] == none['subtitle']
    for name in none['sheets']:
        assert len(_rows(zero['sheets'][name])) == len(_rows(none['sheets'][name]))


def test_excel_sheet_is_not_truncated_to_the_deck_limit(flask_app, monkeypatch):
    """The deck caps at 15 rows and says so in its caption; the workbook must
    still carry every row."""
    import queries
    from exports import overviews
    fake = [{'client': f'Client {i}', 'cod_client': f'K{i}', 'agent': 'A',
             'tip_client': 'X', 'judet_client': 'Y', 'val_neta': 100 - i,
             'marja_bruta': 10, 'marja_bruta_pct': 10.0, 'marja_neta': 10,
             'marja_neta_pct': 10.0, 'ultima_comanda': '2026-01-15',
             'zile_inactiv': 1, 'nr_branduri': 1, 'delta_vn': None}
            for i in range(40)]
    monkeypatch.setattr(queries, 'clients_list', lambda *a, **k: fake)
    with flask_app.app_context():
        ctx = overviews.build_context('clients', AN, None, {})
    assert len(_rows(ctx['sheets'][f'Clienți {AN}'])) == 40
    assert len(ctx['tables'][0]['rows']) == 15
    assert ctx['tables'][0]['title'] == f'Clienți {AN} — top 15 din 40'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_overview_exports.py -q`
Expected: FAIL — `ImportError: cannot import name 'overviews' from 'exports'`.

- [ ] **Step 3: Create `app/exports/overviews.py`**

```python
"""Context builders for the list and report page exports.

`exports.entities` resolves one identifier; these resolve a set of filters.
Both emit the same context dict (see exports.context), so one Excel route and
one PPT route serve every page and the two formats cannot drift apart.

Unlike the entity builders, an empty result is not a 404 here: a filter that
matches nothing is a valid answer and yields an empty sheet.
"""
import queries
from exports.context import SHEET_ROW_LIMIT, pct, period_label, table
from exports.ppt_export import fmt_pct, fmt_ron

# One table filling the slide: left inset, usable width, in inches.
FULL_WIDTH = (0.3, 12.7)


def _totals(rows):
    """(val_neta, marja_bruta, marja_neta) summed over already-filtered rows."""
    return (
        sum((r.get('val_neta') or 0) for r in rows),
        sum((r.get('marja_bruta') or 0) for r in rows),
        sum((r.get('marja_neta') or 0) for r in rows),
    )


def _team(an, luna, max_luna, filters):
    rows_cy = queries.team_table(an, luna=luna, max_luna=max_luna)
    rows_py = queries.team_table(an - 1, luna=luna, max_luna=max_luna)
    vn, mb, mn = _totals(rows_cy)
    left, width = FULL_WIDTH

    return {
        'nav': 'team',
        'title': f"Echipă {an}",
        'filename_base': f'echipa_{an}',
        'cards': [
            ("Val. Netă", fmt_ron(vn)),
            ("Marjă Brută", f"{fmt_ron(mb)} / {fmt_pct(pct(mb, vn))}"),
            ("Marjă Netă", f"{fmt_ron(mn)} / {fmt_pct(pct(mn, vn))}"),
            ("Nr. Agenți", str(len(rows_cy))),
        ],
        'tables': [
            table(f"Echipa {an}", left, width, rows_cy, lambda r: {
                "Agent": (r.get('agent') or "—")[:24],
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB RON": fmt_ron(r.get('marja_bruta')),
                "MB%": fmt_pct(r.get('marja_pct')),
                "MN RON": fmt_ron(r.get('marja_neta')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
                "Clienți": str(r.get('clienti_activi') or 0),
            }),
        ],
        'extra_tables': [],
        'sheets': {
            f'Echipa {an}': rows_cy,
            f'Echipa {an - 1}': rows_py,
        },
        'trend': None,
    }


def _clients(an, luna, max_luna, filters):
    # The page caps at clients_list's default limit for render speed; the
    # workbook is the full-data artifact, so it asks for everything.
    rows = queries.clients_list(
        an,
        search=filters.get('q') or None,
        agent=filters.get('agent') or None,
        churn=filters.get('churn') or None,
        brand=filters.get('brand') or None,
        luna=luna, max_luna=max_luna, limit=SHEET_ROW_LIMIT,
    )
    vn, mb, mn = _totals(rows)
    left, width = FULL_WIDTH

    return {
        'nav': 'clients',
        'title': f"Clienți {an}",
        'filename_base': f'clienti_{an}',
        'cards': [
            ("Val. Netă", fmt_ron(vn)),
            ("Marjă Brută %", fmt_pct(pct(mb, vn))),
            ("Marjă Netă", f"{fmt_ron(mn)} / {fmt_pct(pct(mn, vn))}"),
            ("Nr. Clienți", str(len(rows))),
        ],
        'tables': [
            table(f"Clienți {an}", left, width, rows, lambda r: {
                "Client": (r.get('client') or "—")[:26],
                "Agent": (r.get('agent') or "—")[:14],
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB%": fmt_pct(r.get('marja_bruta_pct')),
                "MN RON": fmt_ron(r.get('marja_neta')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
            }),
        ],
        'extra_tables': [],
        'sheets': {f'Clienți {an}': rows},
        'trend': None,
    }


_BUILDERS = {
    'team': _team,
    'clients': _clients,
}

REPORTS = tuple(_BUILDERS)


def build_context(report, an, luna=None, filters=None):
    """Context for one list/report export, or None when the request is invalid.

    The caller turns None into a 404. `luna` filters to a single month; when it
    is absent the period is year-to-date up to the last month that has data,
    exactly as the pages do. `luna=0` means "no month filter" — the underlying
    queries disagree about what a literal 0 means, so it is normalised here.
    """
    builder = _BUILDERS.get(report)
    if builder is None:
        return None
    if luna == 0:
        luna = None
    if luna and not 1 <= luna <= 12:
        return None
    max_luna = None if luna else queries.max_luna_for_year(an)
    ctx = builder(an, luna, max_luna, filters or {})
    ctx['subtitle'] = period_label(an, luna, max_luna)
    return ctx
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_overview_exports.py -q`
Expected: PASS.

If `test_team_context_shape` fails on the subtitle, check `queries.max_luna_for_year(2026)` — the seed only has January, so `period_label` renders `'2026 · Ian'`.

- [ ] **Step 5: Lint and run the whole suite**

Run: `ruff check . && python -m pytest tests/ -q`
Expected: no lint errors, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/exports/overviews.py tests/test_overview_exports.py
git commit -m "feat(exports): filter-keyed context builders for team and clients"
```

---

### Task 3: Overview builder for `products`

**Files:**
- Modify: `app/exports/overviews.py`
- Test: `tests/test_overview_exports.py`

**Interfaces:**
- Consumes: `queries.products_brands(an, luna=, max_luna=)`, `queries.products_top_skus(an, furnizor=, limit=, search=, luna=, max_luna=)`.
- Produces: `'products'` added to `overviews.REPORTS`. Its context has one table in `tables` (Branduri) and one in `extra_tables` (Top SKU), each `limit=15`, and sheets `{'Branduri': [...], 'Top SKU': [...]}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_overview_exports.py`:

```python
def test_products_context_shape(flask_app):
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('products', AN, None, {})
    assert ctx['nav'] == 'products'
    assert ctx['filename_base'] == f'produse_{AN}'
    assert list(ctx['sheets']) == ['Branduri', 'Top SKU']
    # Seed: two brands (Basilur, Toras), one SKU each.
    assert len(_rows(ctx['sheets']['Branduri'])) == 2
    assert len(_rows(ctx['sheets']['Top SKU'])) == 2
    assert len(ctx['tables']) == 1
    assert len(ctx['extra_tables']) == 1
    assert ctx['extra_tables'][0]['title'] == f'Top SKU {AN}'


def test_products_context_brand_filter_scopes_skus_only(flask_app):
    """The page filters only the SKU table by brand — the brand table always
    shows every brand. The export mirrors that."""
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('products', AN, None, {'brand': 'Basilur'})
    assert [r['sku'] for r in _rows(ctx['sheets']['Top SKU'])] == ['SKU001']
    assert len(_rows(ctx['sheets']['Branduri'])) == 2


def test_products_context_search_filter_reaches_the_sku_query(flask_app):
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('products', AN, None, {'q': 'SKU002'})
    assert [r['sku'] for r in _rows(ctx['sheets']['Top SKU'])] == ['SKU002']


def test_products_context_honours_luna(flask_app):
    from exports import overviews
    with flask_app.app_context():
        empty = overviews.build_context('products', AN, EMPTY_MONTH, {})
    assert not _rows(empty['sheets']['Branduri'])
    assert not _rows(empty['sheets']['Top SKU'])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_overview_exports.py -k products -q`
Expected: FAIL with `TypeError: 'NoneType' object is not subscriptable` — `build_context` returns `None` for an unknown report.

- [ ] **Step 3: Add the builder to `app/exports/overviews.py`**

Insert after `_clients`, and add `'products': _products,` to `_BUILDERS`.

```python
def _products(an, luna, max_luna, filters):
    # The brand table is never brand-filtered — the page filters only the SKU
    # list, and the brand overview is what gives the filtered SKUs context.
    brands = queries.products_brands(an, luna=luna, max_luna=max_luna)
    skus = queries.products_top_skus(
        an,
        furnizor=filters.get('brand') or None,
        search=filters.get('q') or None,
        luna=luna, max_luna=max_luna, limit=SHEET_ROW_LIMIT,
    )
    vn, mb, mn = _totals(brands)
    left, width = FULL_WIDTH

    return {
        'nav': 'products',
        'title': f"Produse {an}",
        'filename_base': f'produse_{an}',
        'cards': [
            ("Val. Netă", fmt_ron(vn)),
            ("Marjă Brută %", fmt_pct(pct(mb, vn))),
            ("Marjă Netă", f"{fmt_ron(mn)} / {fmt_pct(pct(mn, vn))}"),
            ("Branduri / SKU", f"{len(brands)} / {len(skus)}"),
        ],
        'tables': [
            table(f"Branduri {an}", left, width, brands, lambda r: {
                "Brand": (r.get('furnizor') or "—")[:24],
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB RON": fmt_ron(r.get('marja_bruta')),
                "MB%": fmt_pct(r.get('marja_pct')),
                "MN RON": fmt_ron(r.get('marja_neta')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
                "Clienți": str(r.get('nr_clienti') or 0),
                "SKU": str(r.get('nr_sku') or 0),
            }),
        ],
        'extra_tables': [
            table(f"Top SKU {an}", left, width, skus, lambda r: {
                "Produs": (r.get('sku') or "—")[:30],
                "Brand": r.get('furnizor') or "—",
                "Cant.": str(int(r.get('cantitate') or 0)),
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB%": fmt_pct(r.get('marja_bruta_pct')),
                "MN RON": fmt_ron(r.get('marja_neta')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
                "Clienți": str(r.get('nr_clienti') or 0),
            }),
        ],
        'sheets': {
            'Branduri': brands,
            'Top SKU': skus,
        },
        'trend': None,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_overview_exports.py -q`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `ruff check .`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add app/exports/overviews.py tests/test_overview_exports.py
git commit -m "feat(exports): filter-keyed context builder for the products page"
```

---

### Task 4: Overview builder for `basilur`, and honour `curs` in the deck

**Files:**
- Modify: `app/exports/overviews.py`, `app/exports/ppt_export.py:584-596`
- Test: `tests/test_overview_exports.py`

**Interfaces:**
- Consumes: `queries.{basilur_kpi_total, basilur_kpi_per_brand, basilur_monthly_per_brand, basilur_stoc_per_brand, basilur_stoc_detail}`.
- Produces: `'basilur'` added to `overviews.REPORTS`; `overviews.BASILUR_BRANDS: list[str]`; `overviews.basilur_monthly_matrix(rows) -> dict[str, list[float]]`; `overviews.BASILUR_DEFAULT_CURS: float`. The basilur context additionally carries `'curs': float` and `'ppt_builder': Callable[[], BytesIO]`. `ppt_export.build_basilur_ppt` gains a trailing `curs=4.55` keyword argument.

**Note — this task fixes a live bug.** `build_basilur_ppt` hard-codes `R = 4.55`
while `raportare_basilur_excel` honours `?curs`. Today the workbook and the deck
report different USD figures for the same period whenever the owner changes the
rate on the page. Routing both through one context makes the mismatch impossible,
so the parameter has to be threaded through.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_overview_exports.py`:

```python
def test_basilur_context_shape(flask_app):
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('basilur', AN, None, {})
    assert ctx['nav'] == 'basilur'
    assert ctx['filename_base'] == f'raportare_basilur_{AN}_YTD'
    assert list(ctx['sheets']) == [
        'Brand KPIs', 'Monthly Sales', 'Stock by Brand', 'Stock Detail']
    assert callable(ctx['ppt_builder'])
    assert ctx['curs'] == overviews.BASILUR_DEFAULT_CURS
    # The deck is bespoke, so the generic slide inputs stay empty.
    assert ctx['cards'] == []
    assert ctx['tables'] == []


def test_basilur_filename_names_the_month(flask_app):
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('basilur', AN, 1, {})
    assert ctx['filename_base'] == f'raportare_basilur_Ian_{AN}'


def test_basilur_curs_reaches_the_workbook(flask_app):
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('basilur', AN, None, {'curs': 9.10})
    kpi = _rows(ctx['sheets']['Brand KPIs'])
    basilur = next(r for r in kpi if r['Brand'] == 'Basilur')
    # Seed: Basilur val_neta 500 RON -> 500 / 9.10 = 54.9 -> rounds to 55.
    assert basilur['Net Sales (USD)'] == 55
    assert ctx['curs'] == 9.10


@pytest.mark.parametrize('bad', [0, -1, None])
def test_basilur_falls_back_to_the_default_curs(flask_app, bad):
    """A zero or missing rate would divide by zero in every USD figure."""
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('basilur', AN, None, {'curs': bad})
    assert ctx['curs'] == overviews.BASILUR_DEFAULT_CURS


def test_build_basilur_ppt_uses_the_given_curs(flask_app):
    """Regression: the deck used to hard-code 4.55 and ignore ?curs, so the
    workbook and the deck disagreed whenever the owner changed the rate."""
    from exports import ppt_export
    buf = ppt_export.build_basilur_ppt(
        an=AN, period_label='2026 YTD', kpi_total={'val_neta': 910.0},
        kpi_per_brand=[], monthly_data={}, stoc_per_brand=[], stoc_detail=[],
        curs=9.10)
    texts = [sh.text_frame.text for s in Presentation(buf).slides
             for sh in s.shapes if sh.has_text_frame]
    assert any('Rate: 1 USD = 9.1 RON' in t for t in texts)
    assert any('$100' in t for t in texts)  # 910 RON / 9.10
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_overview_exports.py -k basilur -q`
Expected: FAIL — `build_context` returns `None`, and `build_basilur_ppt` raises `TypeError: build_basilur_ppt() got an unexpected keyword argument 'curs'`.

- [ ] **Step 3: Give `build_basilur_ppt` a `curs` parameter**

In `app/exports/ppt_export.py`, change the signature and the rate constant. Nothing else in the function body changes — every USD figure already goes through `R`.

```python
def build_basilur_ppt(an, period_label, kpi_total, kpi_per_brand,
                      monthly_data, stoc_per_brand, stoc_detail, curs=4.55):
    _check()
    BRANDS = ["Basilur", "KingsLeaf", "Tipson", "Organsia"]
```

and replace line 596:

```python
    R = curs or 4.55  # RON → USD; a zero rate would divide by zero below
```

- [ ] **Step 4: Add the basilur builder to `app/exports/overviews.py`**

Add `'basilur': _basilur,` to `_BUILDERS`, extend the import line to
`from exports import ppt_export` at the top of the module, and insert:

```python
BASILUR_BRANDS = ['Basilur', 'KingsLeaf', 'Tipson', 'Organsia']
BASILUR_DEFAULT_CURS = 4.55
MONTHS_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
             'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def basilur_monthly_matrix(rows):
    """(furnizor, luna, val_neta) rows -> {furnizor: [12 values]}."""
    out = {b: [0] * 12 for b in BASILUR_BRANDS}
    for r in rows:
        furn = r['furnizor']
        luna = r['luna']
        if furn in out and luna and 1 <= int(luna) <= 12:
            out[furn][int(luna) - 1] = r['val_neta'] or 0
    return out


def _basilur(an, luna, max_luna, filters):
    """Supplier-facing report: English labels and USD figures by design, and a
    bespoke deck. Only the plumbing is shared — one query pass feeds both
    formats, which is what keeps their USD figures identical."""
    curs = filters.get('curs') or BASILUR_DEFAULT_CURS
    if curs <= 0:
        curs = BASILUR_DEFAULT_CURS

    kpi_total = queries.basilur_kpi_total(an, max_luna=max_luna, luna=luna) or {}
    kpi_per_brand = [dict(r) for r in
                     queries.basilur_kpi_per_brand(an, max_luna=max_luna, luna=luna)]
    monthly = basilur_monthly_matrix(queries.basilur_monthly_per_brand(an))
    stoc_per_brand = [dict(r) for r in queries.basilur_stoc_per_brand()]
    stoc_detail = [dict(r) for r in queries.basilur_stoc_detail()]

    if luna:
        period = f"{MONTHS_EN[luna - 1]} {an}"
        label = f"{MONTHS_RO_SHORT[luna - 1]} {an}"
        subtitle = f"{an} · {MONTHS_RO_FULL[luna - 1]}"
    else:
        ml = max_luna or 1
        period = f"{an} YTD (ian–{MONTHS_RO_SHORT[ml - 1]})"
        label = f"{an}_YTD"
        subtitle = period

    kpi_rows = [{
        'Brand':              r['furnizor'],
        'Net Sales (USD)':    round((r['val_neta'] or 0) / curs, 0),
        'Active Clients':     r['clienti_activi'] or 0,
        'Active SKUs':        r['nr_sku'] or 0,
        'Net Sales PY (USD)': round((r['val_neta_py'] or 0) / curs, 0),
        'YoY Delta %':        r['delta_vn'],
    } for r in kpi_per_brand]

    pivot_rows = []
    for brand in BASILUR_BRANDS:
        vals = monthly.get(brand, [0] * 12)
        row = {'Brand': brand}
        for i, m in enumerate(MONTHS_EN):
            row[m] = round(vals[i] / curs, 0)
        row['TOTAL'] = round(sum(vals) / curs, 0)
        pivot_rows.append(row)
    total_row = {'Brand': 'TOTAL'}
    for i, m in enumerate(MONTHS_EN):
        total_row[m] = round(
            sum(monthly.get(b, [0] * 12)[i] for b in BASILUR_BRANDS) / curs, 0)
    total_row['TOTAL'] = sum(total_row[m] for m in MONTHS_EN)
    pivot_rows.append(total_row)

    stoc_brand_rows = [{
        'Brand':                   r['furnizor'],
        'SKU Count':               r['nr_sku'] or 0,
        'Total Units':             r['total_unitati'] or 0,
        'Acquisition Value (USD)': round((r['valoare_achizitie'] or 0) / curs, 0),
    } for r in stoc_per_brand]

    stoc_sku_rows = [{
        'Brand':                   r['furnizor'],
        'Product Code':            r['cod_produs'],
        'SKU':                     r['sku'],
        'Quantity':                r['cantitate'] or 0,
        'Unit Cost (USD)':         round((r['pret_achizitie'] or 0) / curs, 2),
        'Acquisition Value (USD)': round((r['valoare_achizitie'] or 0) / curs, 0),
        'Days in Stock':           r['nr_zile_stoc'],
        'Entry Date':              r['data_intrare'],
    } for r in stoc_detail]

    def _deck():
        return ppt_export.build_basilur_ppt(
            an=an, period_label=period, kpi_total=dict(kpi_total),
            kpi_per_brand=kpi_per_brand, monthly_data=monthly,
            stoc_per_brand=stoc_per_brand, stoc_detail=stoc_detail, curs=curs)

    return {
        'nav': 'basilur',
        'title': f"Basilur Group {an}",
        'filename_base': f'raportare_basilur_{label}',
        'cards': [],
        'tables': [],
        'extra_tables': [],
        'sheets': {
            'Brand KPIs':     {'rows': kpi_rows,
                               'headers': list(kpi_rows[0]) if kpi_rows else []},
            'Monthly Sales':  {'rows': pivot_rows,
                               'headers': ['Brand'] + MONTHS_EN + ['TOTAL']},
            'Stock by Brand': {'rows': stoc_brand_rows,
                               'headers': list(stoc_brand_rows[0]) if stoc_brand_rows else []},
            'Stock Detail':   {'rows': stoc_sku_rows,
                               'headers': list(stoc_sku_rows[0]) if stoc_sku_rows else []},
        },
        'trend': None,
        'curs': curs,
        'ppt_builder': _deck,
        'subtitle_override': subtitle,
    }
```

Extend the `exports.context` import to bring in the month names:

```python
from exports.context import (MONTHS_RO_FULL, MONTHS_RO_SHORT, SHEET_ROW_LIMIT,
                             pct, period_label, table)
```

- [ ] **Step 5: Let a builder override the subtitle**

`build_basilur_ppt` renders its own English-flavoured period string, so the
basilur context must keep it rather than take `period_label`'s Romanian one.
In `build_context`, replace the unconditional assignment:

```python
    ctx = builder(an, luna, max_luna, filters or {})
    # A builder that renders its own period string (basilur) keeps it.
    ctx['subtitle'] = ctx.pop('subtitle_override', None) or period_label(an, luna, max_luna)
    return ctx
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_overview_exports.py -q`
Expected: PASS.

- [ ] **Step 7: Lint and run the whole suite**

Run: `ruff check . && python -m pytest tests/ -q`
Expected: no lint errors, all tests pass. `tests/test_ppt_primitive.py` also touches `ppt_export` — it must stay green.

- [ ] **Step 8: Commit**

```bash
git add app/exports/overviews.py app/exports/ppt_export.py tests/test_overview_exports.py
git commit -m "feat(exports): basilur context builder, deck honours the curs parameter"
```

---

### Task 5: Wire both dispatchers and redirect the legacy basilur URLs

**Files:**
- Modify: `app/blueprints/reports.py:1-30`, `:133-210`, `:249-300`, `:361-530`
- Test: `tests/test_overview_exports.py`

**Interfaces:**
- Consumes: `overviews.{REPORTS, build_context, BASILUR_BRANDS, basilur_monthly_matrix, BASILUR_DEFAULT_CURS}`.
- Produces: `/export/team|clients|products|basilur` (Excel) and `/export/ppt/team|clients|products|basilur` (PPT). `reports.raportare_basilur_excel` and `reports.raportare_basilur_ppt` survive as 302 redirects.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_overview_exports.py`:

```python
REPORTS = ['team', 'clients', 'products', 'basilur']

EXPECTED_SHEETS = {
    'team': [f'Echipa {AN}', f'Echipa {AN - 1}'],
    'clients': [f'Clienți {AN}'],
    'products': ['Branduri', 'Top SKU'],
    'basilur': ['Brand KPIs', 'Monthly Sales', 'Stock by Brand', 'Stock Detail'],
}


@pytest.mark.parametrize('report', REPORTS)
def test_excel_route_returns_openable_workbook(client, report):
    rv = client.get(f'/export/{report}?an={AN}')
    assert rv.status_code == 200
    assert rv.mimetype == XLSX_MIME
    wb = openpyxl.load_workbook(io.BytesIO(rv.data))
    assert wb.sheetnames == EXPECTED_SHEETS[report]


@pytest.mark.parametrize('report', REPORTS)
def test_ppt_route_returns_openable_deck(client, report):
    rv = client.get(f'/export/ppt/{report}?an={AN}')
    assert rv.status_code == 200
    assert rv.mimetype == PPT_MIME
    assert len(Presentation(io.BytesIO(rv.data)).slides) >= 2


def test_team_excel_no_longer_ignores_luna(client):
    """Regression: /export/team called team_table(an) with no month filter, so
    it shipped a full year while the page showed a single month."""
    rv = client.get(f'/export/team?an={AN}&luna={EMPTY_MONTH}')
    assert rv.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(rv.data))
    assert wb[f'Echipa {AN}']['A1'].value == 'Nu există date pentru acest raport.'


def test_products_excel_honours_the_page_search_filter(client):
    """Regression: /export/products ignored ?q entirely."""
    rv = client.get(f'/export/products?an={AN}&q=SKU002')
    wb = openpyxl.load_workbook(io.BytesIO(rv.data))
    skus = [row[0] for row in wb['Top SKU'].iter_rows(min_row=2, values_only=True)]
    assert skus == ['SKU002']


@pytest.mark.parametrize('report', REPORTS)
@pytest.mark.parametrize('luna', [13, -1])
def test_routes_reject_out_of_range_luna(client, report, luna):
    assert client.get(f'/export/{report}?an={AN}&luna={luna}').status_code == 404
    assert client.get(f'/export/ppt/{report}?an={AN}&luna={luna}').status_code == 404


@pytest.mark.parametrize('report', REPORTS)
def test_routes_deny_role_without_nav_access(client, monkeypatch, report):
    import authz
    monkeypatch.setattr(authz, 'can_access_nav', lambda role, key: False)
    assert client.get(f'/export/{report}?an={AN}').status_code == 403
    assert client.get(f'/export/ppt/{report}?an={AN}').status_code == 403


def test_legacy_basilur_excel_url_redirects(client):
    rv = client.get(f'/raportare-basilur/export/excel?an={AN}&curs=5')
    assert rv.status_code == 302
    assert '/export/basilur' in rv.headers['Location']
    assert 'curs=5' in rv.headers['Location']


def test_legacy_basilur_ppt_url_redirects(client):
    rv = client.get(f'/raportare-basilur/export/ppt?an={AN}&curs=5')
    assert rv.status_code == 302
    assert '/export/ppt/basilur' in rv.headers['Location']
    assert 'curs=5' in rv.headers['Location']


def test_basilur_page_still_renders(client):
    """The page route now imports BASILUR_BRANDS from exports.overviews."""
    rv = client.get(f'/raportare-basilur?an={AN}')
    assert rv.status_code == 200
    assert 'KingsLeaf' in rv.get_data(as_text=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_overview_exports.py -k "route or legacy" -q`
Expected: FAIL — `/export/ppt/team` returns 404, and the legacy URLs return 200 instead of 302.

- [ ] **Step 3: Update the imports and the nav map in `app/blueprints/reports.py`**

```python
from flask import Blueprint, render_template, request, abort, send_file, redirect, url_for
```

and add one entry to `_EXPORT_NAV_KEY`:

```python
    "basilur": "basilur",
```

and extend the exports import:

```python
from exports import entities, overviews, ppt_export
```

- [ ] **Step 4: Add the shared filter parser**

Insert just above `_PPT_ENTITIES` (around line 133):

```python
def _overview_filters(report):
    """Query args each overview export honours — one source of truth for both
    dispatchers, so the Excel and PPT links cannot disagree about the filter."""
    if report == 'clients':
        return {k: request.args.get(k, '').strip()
                for k in ('q', 'agent', 'churn', 'brand')}
    if report == 'products':
        return {k: request.args.get(k, '').strip() for k in ('brand', 'q')}
    if report == 'basilur':
        return {'curs': request.args.get(
            'curs', type=float, default=overviews.BASILUR_DEFAULT_CURS)}
    return {}
```

- [ ] **Step 5: Rewrite `export_ppt`**

Replace the whole function body (lines 181–205). Authz now reads `_EXPORT_NAV_KEY`
for every entity and report, so the nav key lives in exactly one map.

```python
@reports_bp.route('/export/ppt/<entity>')
def export_ppt(entity):
    """Generic multi-feature PPT export — gated per-entity here, which is why
    this endpoint is allow-listed in nav_registry.UNGATED_ENDPOINTS."""
    known = entity in overviews.REPORTS or entity in _PPT_ENTITIES
    nav = _EXPORT_NAV_KEY.get(entity)
    if not known or nav is None:
        abort(404)
    if not authz.can_access_nav(current_user.role, nav):
        abort(403)

    an = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int)

    if entity in overviews.REPORTS:
        ctx = overviews.build_context(entity, an, luna, _overview_filters(entity))
        if ctx is None:
            abort(404)
        builder = ctx.get('ppt_builder')
        buf = builder() if builder else ppt_export.build_entity_ppt(ctx)
        return ppt_export.send_ppt(
            buf, ppt_export.timestamped_filename(ctx['filename_base']))

    param = _PPT_ENTITIES[entity][1]
    if param is None:
        buf, base = _OVERVIEW_PPT[entity](an)
        return ppt_export.send_ppt(buf, ppt_export.timestamped_filename(base))

    ident = request.args.get(param, '').strip()
    ctx = entities.build_context(entity, ident, an, luna) if ident else None
    if ctx is None:
        abort(404)
    buf = ppt_export.build_entity_ppt(ctx)
    return ppt_export.send_ppt(
        buf, ppt_export.timestamped_filename(ctx['filename_base']))
```

- [ ] **Step 6: Replace the three hand-rolled Excel branches**

In `export_excel`, delete the `if report == 'team':`, `if report == 'clients':`
and `if report == 'products':` blocks entirely, and insert this immediately after
the authz check:

```python
    if report in overviews.REPORTS:
        luna = request.args.get('luna', type=int)
        ctx = overviews.build_context(report, an, luna, _overview_filters(report))
        if ctx is None:
            abort(404)
        return send_excel(ctx['sheets'],
                          timestamped_filename(ctx['filename_base']))
```

- [ ] **Step 7: Point the basilur page route at `overviews`, and redirect the legacy URLs**

Delete `BASILUR_BRANDS` and `_basilur_monthly_matrix` from `reports.py` and the
whole bodies of `raportare_basilur_excel` and `raportare_basilur_ppt`. In
`raportare_basilur`, replace the two references:

```python
    monthly_data  = overviews.basilur_monthly_matrix(monthly_rows)
```

```python
    for b in overviews.BASILUR_BRANDS:
```
(both loops — the `kpi_map` one and the `stoc_map` one), and the template arg:

```python
        basilur_brands=overviews.BASILUR_BRANDS,
```

Also switch the `curs` default so page and export agree:

```python
    usd_rate = request.args.get('curs', type=float,
                                default=overviews.BASILUR_DEFAULT_CURS)
```

Then replace the two export routes with:

```python
def _forward_args(*drop):
    args = request.args.to_dict()
    for key in drop:
        args.pop(key, None)
    return args


@reports_bp.route('/raportare-basilur/export/excel')
def raportare_basilur_excel():
    """Kept so bookmarked links survive — the export moved to the generic
    dispatcher, which is the only place that builds a basilur context."""
    return redirect(url_for('reports.export_excel', report='basilur',
                            **_forward_args('report')))


@reports_bp.route('/raportare-basilur/export/ppt')
def raportare_basilur_ppt():
    """Kept so bookmarked links survive — see raportare_basilur_excel."""
    return redirect(url_for('reports.export_ppt', entity='basilur',
                            **_forward_args('entity')))
```

`MONTHS_RO` stays in `reports.py` — the page route still uses it for its
`period_label` / `period_label_py` template variables.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python -m pytest tests/test_overview_exports.py tests/test_entity_exports.py -q`
Expected: PASS.

- [ ] **Step 9: Run the whole suite and lint**

Run: `ruff check . && python -m pytest tests/ -q`
Expected: no lint errors, all tests pass. `tests/test_endpoint_coverage.py` and
`tests/test_nav_registry.py` must stay green — the two legacy endpoints still
exist (as redirects) and are still listed on the basilur `NavItem`.

- [ ] **Step 10: Commit**

```bash
git add app/blueprints/reports.py tests/test_overview_exports.py
git commit -m "feat(exports): route list pages and basilur through the generic export dispatchers"
```

---

### Task 6: Export buttons on the four pages

**Files:**
- Modify: `app/templates/team.html:5-7`, `app/templates/clients.html:5-7`, `app/templates/products.html:5-7`, `app/templates/raportare_basilur.html:30-37`
- Test: `tests/test_overview_exports.py`

**Interfaces:**
- Consumes: the routes from Task 5.
- Produces: no Python surface. Template context variables used: `an`, `luna` (all four), `q`/`sel_agent`/`sel_churn`/`sel_brand` (clients), `sel_brand`/`sel_search` (products), `usd_rate` (basilur).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_overview_exports.py`:

```python
PAGE_URL = {
    'team': '/team',
    'clients': '/clients',
    'products': '/products',
    'basilur': '/raportare-basilur',
}


@pytest.mark.parametrize('report', REPORTS)
def test_page_offers_both_exports(client, report):
    html = client.get(f'{PAGE_URL[report]}?an={AN}').get_data(as_text=True)
    assert f'/export/{report}?' in html
    assert f'/export/ppt/{report}?' in html


def test_clients_page_export_links_carry_the_active_filters(client):
    html = client.get(f'/clients?an={AN}&agent=Agent+Test&brand=Basilur').get_data(as_text=True)
    assert 'agent=Agent+Test' in html
    assert 'brand=Basilur' in html


def test_products_page_export_links_carry_the_active_filters(client):
    html = client.get(f'/products?an={AN}&brand=Basilur&q=SKU001').get_data(as_text=True)
    assert 'q=SKU001' in html


def test_basilur_page_export_links_carry_the_rate(client):
    html = client.get(f'/raportare-basilur?an={AN}&curs=5.1').get_data(as_text=True)
    assert 'curs=5.1' in html
```

Confirm the page URLs first — run `python -m pytest tests/test_flask_routes.py -q`
if any 404, and read `app/nav_registry.py:31-45` for the canonical endpoints.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_overview_exports.py -k page -q`
Expected: FAIL — `assert '/export/ppt/team?' in html`.

- [ ] **Step 3: Add the buttons to `app/templates/team.html`**

Replace lines 5–7 with:

```html
<div class="d-flex justify-content-between align-items-center mb-2">
  <h4 class="mb-0 fw-bold"><i class="bi bi-people-fill text-primary"></i> Performanță Echipă</h4>
  <div class="d-flex gap-2 align-items-center">
    <a href="{{ url_for('reports.export_excel', report='team', an=an, luna=luna) }}"
       class="btn btn-sm btn-outline-success" title="Export Excel">
      <i class="bi bi-file-earmark-excel"></i> Excel
    </a>
    <a href="{{ url_for('reports.export_ppt', entity='team', an=an, luna=luna) }}"
       class="btn btn-sm btn-outline-danger" title="Export PPT">
      <i class="bi bi-file-earmark-slides"></i> PPT
    </a>
  </div>
</div>
```

- [ ] **Step 4: Add the buttons to `app/templates/clients.html`**

Replace lines 5–7 with:

```html
<div class="d-flex justify-content-between align-items-center mb-2">
  <h4 class="mb-0 fw-bold"><i class="bi bi-building text-primary"></i> Clienți</h4>
  <div class="d-flex gap-2 align-items-center">
    <a href="{{ url_for('reports.export_excel', report='clients', an=an, luna=luna,
                        q=q, agent=sel_agent, churn=sel_churn, brand=sel_brand) }}"
       class="btn btn-sm btn-outline-success" title="Export Excel">
      <i class="bi bi-file-earmark-excel"></i> Excel
    </a>
    <a href="{{ url_for('reports.export_ppt', entity='clients', an=an, luna=luna,
                        q=q, agent=sel_agent, churn=sel_churn, brand=sel_brand) }}"
       class="btn btn-sm btn-outline-danger" title="Export PPT">
      <i class="bi bi-file-earmark-slides"></i> PPT
    </a>
  </div>
</div>
```

- [ ] **Step 5: Add the buttons to `app/templates/products.html`**

Replace lines 5–7 with:

```html
<div class="d-flex justify-content-between align-items-center mb-2">
  <h4 class="mb-0 fw-bold"><i class="bi bi-box-seam-fill text-primary"></i> Produse & Branduri</h4>
  <div class="d-flex gap-2 align-items-center">
    <a href="{{ url_for('reports.export_excel', report='products', an=an, luna=luna,
                        brand=sel_brand, q=sel_search) }}"
       class="btn btn-sm btn-outline-success" title="Export Excel">
      <i class="bi bi-file-earmark-excel"></i> Excel
    </a>
    <a href="{{ url_for('reports.export_ppt', entity='products', an=an, luna=luna,
                        brand=sel_brand, q=sel_search) }}"
       class="btn btn-sm btn-outline-danger" title="Export PPT">
      <i class="bi bi-file-earmark-slides"></i> PPT
    </a>
  </div>
</div>
```

- [ ] **Step 6: Repoint the basilur buttons**

In `app/templates/raportare_basilur.html`, replace lines 30–37 with:

```html
    <a href="{{ url_for('reports.export_excel', report='basilur', an=an, luna=luna or '', curs=usd_rate) }}"
       class="btn btn-sm btn-outline-success">
      <i class="bi bi-file-earmark-excel me-1"></i>Export Excel
    </a>
    <a href="{{ url_for('reports.export_ppt', entity='basilur', an=an, luna=luna or '', curs=usd_rate) }}"
       class="btn btn-sm btn-outline-danger">
      <i class="bi bi-file-earmark-slides me-1"></i>Export PPT
    </a>
```

The colour changes from `btn-outline-primary` to `btn-outline-danger` so the PPT
button matches every other page.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_overview_exports.py -q`
Expected: PASS.

- [ ] **Step 8: Run the whole suite**

Run: `ruff check . && python -m pytest tests/ -q`
Expected: no lint errors, all tests pass. `tests/test_nav_render.py` and
`tests/test_static_css.py` also render templates — they must stay green.

- [ ] **Step 9: Commit**

```bash
git add app/templates/team.html app/templates/clients.html app/templates/products.html app/templates/raportare_basilur.html tests/test_overview_exports.py
git commit -m "feat(ui): Excel and PPT export buttons on the team, clients, products and basilur pages"
```

---

### Task 7: Documentation

**Files:**
- Modify: `CHANGELOG.md`, `context/STATUS.md`, `docs/TECHNICAL.md`

**Interfaces:**
- Consumes: everything above.
- Produces: no code surface.

- [ ] **Step 1: Invoke the documentation skill**

Use the `updating-documentation` skill — this round changed behaviour, so it
applies. Follow its routing rather than guessing which files to touch.

- [ ] **Step 2: Add a `[Unreleased]` CHANGELOG entry**

Cover, in this order: the four pages gaining Excel + PPT; `luna` now honoured by
the team/clients/products exports (previously dropped); the products export now
honouring `?q`; basilur's deck now honouring `?curs` (it hard-coded 4.55, so the
workbook and the deck disagreed whenever the owner changed the rate); the two
legacy basilur export URLs becoming redirects.

- [ ] **Step 3: Update `context/STATUS.md`**

Bump **Ultima actualizare** to the implementation date and add one line under
"Livrat recent", pointing at CHANGELOG for detail. Do not restate the
implementation there — that is CHANGELOG's job.

- [ ] **Step 4: Note the export architecture in `docs/TECHNICAL.md`**

One short paragraph: `exports/context.py` holds the shared primitives,
`exports/entities.py` is ident-keyed, `exports/overviews.py` is filter-keyed,
both feed the same two dispatchers.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md context/STATUS.md docs/TECHNICAL.md
git commit -m "docs: record the overview export standardisation"
```

---

## Verification

Before declaring the work complete:

```bash
ruff check .
python -m pytest tests/ -q
```

Both must pass with zero errors. Then start the app and click all eight buttons —
the workbook and the deck for the same page and period must report the same
figures.
