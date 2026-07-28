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


def _brand_mix(products):
    """Period-scoped Brand Mix, aggregated in Python from the already period-
    filtered product rows — client_brand_mix has no luna/max_luna and would
    reintroduce the exact period drift this module exists to eliminate."""
    totals = {}
    for r in products:
        furnizor = r.get('furnizor')
        totals[furnizor] = totals.get(furnizor, 0) + (r.get('val_neta') or 0)
    rows = [{'furnizor': furnizor, 'val_neta': val_neta} for furnizor, val_neta in totals.items()]
    rows.sort(key=lambda r: r['val_neta'], reverse=True)
    return rows


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
            ("Marjă Netă", f"{fmt_ron(mn)} / {fmt_pct(_pct(mn, vn))}"),
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
            'Brand Mix': _brand_mix(products),
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
    monthly = queries.agent_monthly_full(name)

    return {
        'nav': 'team',
        'title': f"Agent: {name}",
        'filename_base': _slug_with_year('agent', name, an, 40),
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
            'Trend Lunar': monthly,
        },
        'trend': _trend(monthly),
    }


def _brand(furnizor, an, luna, max_luna):
    kpi = queries.brand_kpi(furnizor, an, max_luna=max_luna, luna=luna)
    if not kpi or not kpi.get('val_neta'):
        return None
    clients = queries.brand_clients(furnizor, an, max_luna=max_luna, luna=luna,
                                     limit=SHEET_ROW_LIMIT)
    skus = queries.products_top_skus(an, furnizor=furnizor, limit=SHEET_ROW_LIMIT,
                                     luna=luna, max_luna=max_luna)
    monthly = queries.brand_monthly_full(furnizor)

    return {
        'nav': 'products',
        'title': f"Brand: {furnizor}",
        'filename_base': _slug_with_year('brand', furnizor, an, 40),
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
            'Trend Lunar': monthly,
        },
        'trend': _trend(monthly),
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
        'filename_base': _slug_with_year('produs', sku, an, 40),
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
    # luna=0 is ambiguous downstream: brand_kpi/agent_kpi test `luna is not
    # None` (0 becomes `luna = 0`, matching nothing) while product_kpi/
    # client_products_full test truthiness (0 falls through to year-to-date).
    # Normalize here so all four entities agree on "no month filter".
    if luna == 0:
        luna = None
    if luna and not 1 <= luna <= 12:
        return None
    max_luna = None if luna else queries.max_luna_for_year(an)
    ctx = builder(ident, an, luna, max_luna)
    if ctx is not None:
        ctx['subtitle'] = _period_label(an, luna, max_luna)
    return ctx
