"""Context builders for the list and report page exports.

`exports.entities` resolves one identifier; these resolve a set of filters.
Both emit the same context dict (see exports.context), so one Excel route and
one PPT route serve every page and the two formats cannot drift apart.

Unlike the entity builders, an empty result is not a 404 here: a filter that
matches nothing is a valid answer and yields an empty sheet.
"""
import queries
from exports import ppt_export
from exports.context import (MONTHS_RO_FULL, MONTHS_RO_SHORT, SHEET_ROW_LIMIT,
                             pct, period_label, table)
from exports.ppt_export import fmt_pct, fmt_ron

# One table filling the slide: left inset, usable width, in inches.
FULL_WIDTH = (0.3, 12.7)

BASILUR_BRANDS = ['Basilur', 'KingsLeaf', 'Tipson', 'Organsia']
BASILUR_DEFAULT_CURS = 4.55
MONTHS_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
             'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def basilur_monthly_matrix(rows):
    """(furnizor, luna, val_achizitie) rows -> {furnizor: [12 values]}."""
    out = {b: [0] * 12 for b in BASILUR_BRANDS}
    for r in rows:
        furn = r['furnizor']
        luna = r['luna']
        if furn in out and luna and 1 <= int(luna) <= 12:
            out[furn][int(luna) - 1] = r['val_achizitie'] or 0
    return out


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
        label = f"{MONTHS_RO_SHORT[luna - 1]}_{an}"
        subtitle = f"{an} · {MONTHS_RO_FULL[luna - 1]}"
    else:
        ml = max_luna or 1
        period = f"{an} YTD (ian–{MONTHS_RO_SHORT[ml - 1]})"
        label = f"{an}_YTD"
        subtitle = period

    kpi_rows = [{
        'Brand':                 r['furnizor'],
        'Sales at Cost (USD)':   round((r['val_achizitie'] or 0) / curs, 0),
        'Active Clients':        r['clienti_activi'] or 0,
        'Active SKUs':           r['nr_sku'] or 0,
        'Sales at Cost PY (USD)': round((r['val_achizitie_py'] or 0) / curs, 0),
        'YoY Delta %':           r['delta_vn'],
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
            'Monthly Sales at Cost': {'rows': pivot_rows,
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


_BUILDERS = {
    'team': _team,
    'clients': _clients,
    'products': _products,
    'basilur': _basilur,
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
    # A builder that renders its own period string (basilur) keeps it.
    ctx['subtitle'] = ctx.pop('subtitle_override', None) or period_label(an, luna, max_luna)
    return ctx
