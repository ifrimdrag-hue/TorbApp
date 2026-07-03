"""
Procurement forecast logic — seasonality-adjusted order suggestions.
"""
import calendar
import datetime
import logging
import re
from collections import defaultdict

from db import query, query_one

logger = logging.getLogger(__name__)

MONTHS_RO = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
             'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

SAFETY_DAYS = 30


def get_export_codes() -> tuple:
    """Lista cod_client pentru clienții export, citită dinamic din DB.

    Configurabilă din UI (tab Setări → Clienți Export). Doar clienții
    activi sunt incluși în calculul sugestiei de comandă export.
    """
    try:
        rows = query("SELECT cod_client FROM clienti_export WHERE activ = 1")
        return tuple(r['cod_client'] for r in rows)
    except Exception:
        logger.warning("get_export_codes failed", exc_info=True)
        return ()


def _normalize_sku(sku: str) -> str:
    """Normalize SKU variants so ERP-format and stoc-format match.

    ERP sometimes exports the EAN code without parentheses:
      'T.CIOC N CU MENTA FZG 75GR-534 8410342003218'
    Stoc always stores it with parentheses:
      'T.CIOC N CU MENTA FZG 75GR-534 (8410342003218)'
    Wrap the bare trailing EAN (8-13 digits) with parens so both map to
    the same key and stock is matched correctly.
    """
    if not sku:
        return sku
    return re.sub(r'\s+(\d{8,13})\s*$', r' (\1)', sku.strip())


def _next_month_start(d: datetime.date) -> datetime.date:
    if d.month == 12:
        return datetime.date(d.year + 1, 1, 1)
    return datetime.date(d.year, d.month + 1, 1)


def get_lead_time(furnizor: str) -> dict:
    try:
        row = query_one(
            "SELECT zile_livrare, sezon_craciun, observatii FROM termene_aprovizionare WHERE furnizor = :f",
            {'f': furnizor}
        )
        return dict(row) if row else {'zile_livrare': 30, 'sezon_craciun': 0, 'observatii': None}
    except Exception:
        logger.warning("get_lead_time failed for %s", furnizor, exc_info=True)
        return {'zile_livrare': 30, 'sezon_craciun': 0, 'observatii': None}


def get_in_transit(furnizor: str) -> dict:
    """Returns {sku: qty} for orders in emisa / confirmata / in_tranzit status."""
    try:
        rows = query("""
            SELECT l.sku,
                   SUM(COALESCE(l.cantitate_confirmata, l.cantitate_comandata)) AS qty
            FROM comenzi_furnizori_linii l
            JOIN comenzi_furnizori c ON c.id = l.comanda_id
            WHERE c.furnizor = :f
              AND c.status IN ('emisa', 'confirmata', 'in_tranzit',
                               'Emisa', 'Confirmata', 'In tranzit')
            GROUP BY l.sku
        """, {'f': furnizor})
        return {_normalize_sku(r['sku']): (r['qty'] or 0) for r in rows}
    except Exception:
        logger.warning("get_in_transit failed for %s", furnizor, exc_info=True)
        return {}


def _monthly_sales_by_sku(furnizor: str) -> dict:
    """
    Returns {sku: {'ro': {month: avg}, 'export': {month: avg},
                   'total': {month: avg}, 'cod_produs': str}}
    averaged across available years (up to 3 years of history).

    'export' = vânzări către clienții HU (Brandmix + Hun-Trade), urmăriți
    separat pentru sugestii de comandă export distinctă.
    'ro' = piața RO (toate celelalte vânzări).
    'total' = ro + export (preluat ca avg_monthly în sugestie).
    """
    cutoff_year = datetime.date.today().year - 3
    export_clause = "cod_client IN (SELECT cod_client FROM clienti_export WHERE activ = 1)"
    rows = query(f"""
        SELECT t.sku, t.luna, t.an,
               SUM(CASE WHEN {export_clause} THEN cantitate ELSE 0 END) AS qty_exp,
               SUM(CASE WHEN NOT ({export_clause}) OR cod_client IS NULL
                        THEN cantitate ELSE 0 END) AS qty_ro
        FROM tranzactii t
        WHERE t.furnizor = :f AND t.an >= :cutoff
        GROUP BY t.sku, t.luna, t.an
        ORDER BY t.sku, t.luna, t.an
    """, {'f': furnizor, 'cutoff': cutoff_year})

    raw_ro = defaultdict(lambda: defaultdict(list))
    raw_exp = defaultdict(lambda: defaultdict(list))

    for r in rows:
        sku_n = _normalize_sku(r['sku'])
        m = int(r['luna'])
        raw_ro[sku_n][m].append(r['qty_ro'] or 0)
        raw_exp[sku_n][m].append(r['qty_exp'] or 0)

    all_skus = set(raw_ro.keys()) | set(raw_exp.keys())
    result = {}
    for sku in all_skus:
        ro = {m: sum(q) / len(q) for m, q in raw_ro[sku].items() if q}
        exp = {m: sum(q) / len(q) for m, q in raw_exp[sku].items() if q}
        total = {m: ro.get(m, 0) + exp.get(m, 0) for m in set(ro.keys()) | set(exp.keys())}
        result[sku] = {
            'ro': ro,
            'export': exp,
            'total': total,
            'cod_produs': None,
        }
    return result


def _seasonality_index(monthly_avg: dict) -> dict:
    """Returns {month: index} where 1.0 = average month."""
    total = sum(monthly_avg.values())
    if total == 0:
        return {m: 1.0 for m in range(1, 13)}
    avg = total / 12
    return {m: round((monthly_avg.get(m, 0) / avg), 2) for m in range(1, 13)}


def _coverage_demand(monthly_avg: dict, lead_time_days: int) -> float:
    """
    Sum of expected demand from today through (today + lead_time + SAFETY_DAYS).
    Uses per-month daily rates adjusted for the fraction of each month covered.
    """
    today = datetime.date.today()
    end = today + datetime.timedelta(days=lead_time_days + SAFETY_DAYS)
    total = 0.0
    cur = today
    while cur <= end:
        m = cur.month
        y = cur.year
        days_in_m = calendar.monthrange(y, m)[1]
        month_end = datetime.date(y, m, days_in_m)
        covered_end = min(month_end, end)
        days_covered = (covered_end - cur).days + 1
        daily = (monthly_avg.get(m, 0) / days_in_m) if days_in_m else 0
        total += daily * days_covered
        cur = _next_month_start(covered_end)
    return total


def _listing_changes(furnizor: str) -> dict:
    """
    Returns {sku: {'new': N, 'lost': N}} — clients listing/delisting vs same period last year.
    """
    try:
        rows = query("""
            WITH recent AS (
                SELECT sku, cod_client FROM tranzactii
                WHERE furnizor = :f AND data_dl >= date('now', '-90 days')
                GROUP BY sku, cod_client
            ),
            prev AS (
                SELECT sku, cod_client FROM tranzactii
                WHERE furnizor = :f
                  AND data_dl >= date('now', '-455 days')
                  AND data_dl <  date('now', '-365 days')
                GROUP BY sku, cod_client
            ),
            all_pairs AS (
                SELECT sku, cod_client FROM recent
                UNION
                SELECT sku, cod_client FROM prev
            )
            SELECT a.sku,
                   SUM(CASE WHEN r.cod_client IS NOT NULL AND p.cod_client IS NULL THEN 1 ELSE 0 END) AS new_c,
                   SUM(CASE WHEN r.cod_client IS NULL AND p.cod_client IS NOT NULL THEN 1 ELSE 0 END) AS lost_c
            FROM all_pairs a
            LEFT JOIN recent r USING (sku, cod_client)
            LEFT JOIN prev   p USING (sku, cod_client)
            GROUP BY a.sku
        """, {'f': furnizor})
        return {r['sku']: {'new': r['new_c'] or 0, 'lost': r['lost_c'] or 0} for r in rows}
    except Exception:
        logger.warning("_listing_changes failed for %s", furnizor, exc_info=True)
        return {}


def is_xmas_window() -> bool:
    return datetime.date.today().month in (4, 5)


def build_suggestion(furnizor: str, min_velocity: float = 1.0, only_needed: bool = True) -> dict:
    """
    Build order suggestion for a brand.
    min_velocity : ignore SKUs with avg monthly sales below this threshold
    only_needed  : if True, return only SKUs where suggested > 0
    """
    lt = get_lead_time(furnizor)
    lead_days = lt['zile_livrare']
    sezon_c = lt.get('sezon_craciun', 0)

    today = datetime.date.today()
    delivery_date = today + datetime.timedelta(days=lead_days)

    monthly_data = _monthly_sales_by_sku(furnizor)
    if not monthly_data:
        return {'items': [], 'lead_time': lt, 'xmas_window': is_xmas_window(),
                'delivery_date': delivery_date.isoformat(),
                'snapshot_date': _latest_snapshot()}

    in_transit = get_in_transit(furnizor)
    changes = _listing_changes(furnizor)

    # Also get current stock
    try:
        stock_rows = query("""
            SELECT sku, MAX(cod_mare) AS cod, SUM(cantitate) AS qty,
                   ROUND(SUM(cantitate * pret_achizitie), 2) AS val
            FROM stoc
            WHERE data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
              AND furnizor = :f AND cantitate > 0
            GROUP BY sku
        """, {'f': furnizor})
        stock = {r['sku']: {'qty': r['qty'] or 0, 'val': r['val'] or 0,
                            'cod': str(r['cod']) if r['cod'] else None}
                 for r in stock_rows}
    except Exception:
        logger.warning("stock query failed for %s", furnizor, exc_info=True)
        stock = {}

    # Product descriptions
    try:
        desc_rows = query("SELECT sku, descriere FROM produse WHERE furnizor = :f", {'f': furnizor})
        desc = {r['sku']: r['descriere'] for r in desc_rows}
    except Exception:
        logger.warning("product descriptions query failed for %s", furnizor, exc_info=True)
        desc = {}

    # Prețuri achiziție din costuri_landing (ultimul an disponibil per SKU)
    brand_moneda = lt.get('moneda', 'EUR') or 'EUR'
    try:
        price_rows = query("""
            SELECT cl.sku, cl.pret_achizitie_valuta, cl.moneda
            FROM costuri_landing cl
            WHERE cl.sku IN (
                SELECT DISTINCT sku FROM stoc WHERE furnizor = :f
            )
            AND cl.an = (SELECT MAX(an) FROM costuri_landing WHERE sku = cl.sku)
        """, {'f': furnizor})
        prices = {r['sku']: {'pret_valuta': r['pret_achizitie_valuta'],
                              'moneda': r['moneda'] or brand_moneda}
                  for r in price_rows}
    except Exception:
        logger.warning("price query failed for %s", furnizor, exc_info=True)
        prices = {}

    all_skus = sorted(set(monthly_data.keys()) | set(stock.keys()))

    items = []
    for sku in all_skus:
        sku_data = monthly_data.get(sku, {})
        if not sku_data:
            continue
        sku_monthly_total = sku_data.get('total', {})
        sku_monthly_ro = sku_data.get('ro', {})
        sku_monthly_export = sku_data.get('export', {})

        avg_monthly = sum(sku_monthly_total.values()) / 12 if sku_monthly_total else 0
        avg_monthly_ro = sum(sku_monthly_ro.values()) / 12 if sku_monthly_ro else 0
        avg_monthly_export = sum(sku_monthly_export.values()) / 12 if sku_monthly_export else 0

        # Filter slow movers
        if avg_monthly < min_velocity:
            continue

        stoc_qty = stock.get(sku, {}).get('qty', 0)
        stoc_val = stock.get(sku, {}).get('val', 0)
        transit_qty = in_transit.get(sku, 0)
        cod_produs = stock.get(sku, {}).get('cod') or sku_data.get('cod_produs')

        demand_total = _coverage_demand(sku_monthly_total, lead_days)
        demand_ro = _coverage_demand(sku_monthly_ro, lead_days)
        demand_export = _coverage_demand(sku_monthly_export, lead_days)
        s_idx = _seasonality_index(sku_monthly_total)

        zile_stoc = None
        if avg_monthly > 0:
            total_available = stoc_qty + transit_qty
            zile_stoc = int(total_available / (avg_monthly / 30))

        # Stocul comun + tranzitul acopera intai cererea RO; surplusul
        # ramane disponibil pentru export. Comanda separata catre furnizor
        # pentru export = demand_export - surplus.
        available = stoc_qty + transit_qty
        suggested_ro = max(0, round(demand_ro - available))
        surplus_dupa_ro = max(0, available - demand_ro)
        suggested_export = max(0, round(demand_export - surplus_dupa_ro))
        suggested_total = suggested_ro + suggested_export

        is_xmas = bool(sezon_c) and (s_idx.get(10, 0) > 1.3 or s_idx.get(11, 0) > 1.3)

        if zile_stoc is not None and zile_stoc < lead_days:
            urgenta = 'critic'
        elif zile_stoc is not None and zile_stoc < lead_days + 30:
            urgenta = 'atentie'
        else:
            urgenta = 'ok'

        # Next 6 months breakdown for display
        months_detail = []
        for offset in range(6):
            m_num = (today.month - 1 + offset) % 12 + 1
            months_detail.append({
                'label': MONTHS_RO[m_num - 1],
                'avg': round(sku_monthly_total.get(m_num, 0), 1),
                'idx': s_idx.get(m_num, 1.0),
            })

        chg = changes.get(sku, {'new': 0, 'lost': 0})

        price_info = prices.get(sku, {})
        items.append({
            'sku': sku,
            'cod_produs': cod_produs,
            'descriere': desc.get(sku, ''),
            'pret_valuta': price_info.get('pret_valuta'),
            'moneda': price_info.get('moneda', brand_moneda),
            'stoc_qty': stoc_qty,
            'stoc_val': stoc_val,
            'in_tranzit': transit_qty,
            'avg_monthly': round(avg_monthly, 1),
            'avg_monthly_ro': round(avg_monthly_ro, 1),
            'avg_monthly_export': round(avg_monthly_export, 1),
            'demand': round(demand_total, 1),
            'demand_ro': round(demand_ro, 1),
            'demand_export': round(demand_export, 1),
            'zile_stoc': zile_stoc,
            'suggested': suggested_total,
            'suggested_ro': suggested_ro,
            'suggested_export': suggested_export,
            'ordered': suggested_total,
            'urgenta': urgenta,
            'is_xmas': is_xmas,
            'delivery_date': delivery_date.isoformat(),
            'months': months_detail,
            'new_clients': chg['new'],
            'lost_clients': chg['lost'],
        })

    if only_needed:
        items = [i for i in items if i['suggested'] > 0]

    urgency_order = {'critic': 0, 'atentie': 1, 'ok': 2}
    items.sort(key=lambda x: (urgency_order[x['urgenta']], -x['suggested']))

    return {
        'items': items,
        'lead_time': lt,
        'xmas_window': is_xmas_window(),
        'delivery_date': delivery_date.isoformat(),
        'snapshot_date': _latest_snapshot(),
    }


def _latest_snapshot() -> str | None:
    try:
        row = query_one("SELECT MAX(data_snapshot) AS d FROM stoc")
        return row['d'] if row else None
    except Exception:
        logger.warning("_latest_snapshot failed", exc_info=True)
        return None
