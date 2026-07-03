from db import query, query_one
from queries._shared import _years_params, display_years


def forecast_stoc(gama=None, urgenta=None):
    """
    Stoc curent + viteză vânzări → zile stoc rămase.
    urgenta: 'critic' (<30z), 'atentie' (30-60z), 'ok' (>60z), None = toate
    """
    filters, params = [], {}
    if gama:
        filters.append("s.gama = :gama")
        params["gama"] = gama
    where = ("AND " + " AND ".join(filters)) if filters else ""

    rows = query(f"""
        SELECT
            s.sku,
            s.furnizor,
            s.gama,
            SUM(s.cantitate)                               AS stoc_total,
            ROUND(SUM(s.cantitate * s.pret_achizitie), 2)  AS valoare_stoc,
            COALESCE(ROUND(v.vanzari_luna_avg, 1), 0)      AS vanzari_luna_avg,
            CASE
                WHEN COALESCE(v.vanzari_luna_avg, 0) > 0
                THEN CAST(ROUND(SUM(s.cantitate) / (v.vanzari_luna_avg / 30.0)) AS INTEGER)
                ELSE NULL
            END                                            AS zile_stoc,
            MIN(s.data_intrare)                            AS cel_mai_vechi_lot,
            MAX(s.nr_zile_stoc)                            AS max_zile_in_stoc
        FROM stoc s
        LEFT JOIN (
            SELECT sku, SUM(cantitate) / 3.0 AS vanzari_luna_avg
            FROM tranzactii
            WHERE data_dl >= date('now', '-90 days')
            GROUP BY sku
        ) v ON s.sku = v.sku
        WHERE s.data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
          AND s.cantitate > 0
          {where}
        GROUP BY s.sku, s.furnizor, s.gama
        ORDER BY zile_stoc ASC, valoare_stoc DESC
    """, params)

    if urgenta == "critic":
        rows = [r for r in rows if r["zile_stoc"] is not None and r["zile_stoc"] < 30]
    elif urgenta == "atentie":
        rows = [r for r in rows if r["zile_stoc"] is not None and 30 <= r["zile_stoc"] < 60]
    elif urgenta == "ok":
        rows = [r for r in rows if r["zile_stoc"] is None or r["zile_stoc"] >= 60]

    return rows


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


def forecast_gama_list():
    return query("""
        SELECT DISTINCT gama FROM stoc
        WHERE data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
          AND gama IS NOT NULL
        ORDER BY gama
    """)


# ── Profitabilitate completă: MB + MN la nivel agent / client / produs ────────

# CTE that computes net commercial condition cost aggregated to cod_client level.
# Produces ONE row per cod_client so it can be joined safely in GROUP BY queries
# without multiplying costs across transaction rows.
# Uses UNION ALL instead of OR clauses to allow SQLite to use indexes (~10x faster).
_COND_EXPR = (
    "CASE WHEN c.tip_valoare='pct'       THEN b.val_neta * c.valoare / 100.0 "
    "     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END"
)

_COND_CTE = """
    base_cf AS (
        SELECT cod_client, furnizor, SUM(val_neta) AS val_neta
        FROM tranzactii WHERE {where_inner}
        GROUP BY cod_client, furnizor
    ),
    cond_matched AS (
        SELECT b.cod_client, """ + _COND_EXPR + """ AS cost
        FROM base_cf b JOIN conditii_comerciale c
            ON c.an = :an AND c.cod_client = b.cod_client AND c.furnizor = b.furnizor
        UNION ALL
        SELECT b.cod_client, """ + _COND_EXPR + """
        FROM base_cf b JOIN conditii_comerciale c
            ON c.an = :an AND c.cod_client = b.cod_client AND c.furnizor IS NULL
        UNION ALL
        SELECT b.cod_client, """ + _COND_EXPR + """
        FROM base_cf b JOIN conditii_comerciale c
            ON c.an = :an AND c.cod_client IS NULL AND c.furnizor = b.furnizor
        UNION ALL
        SELECT b.cod_client, """ + _COND_EXPR + """
        FROM base_cf b JOIN conditii_comerciale c
            ON c.an = :an AND c.cod_client IS NULL AND c.furnizor IS NULL
    ),
    cond_cost AS (
        SELECT cod_client, ROUND(SUM(cost), 4) AS cost_conditii
        FROM cond_matched GROUP BY cod_client
    )
"""



def forecast_stoc_brand(furnizor=None, gama=None, urgenta=None, search=None):
    """Stoc curent + vânzări recente + comenzi în tranzit (per-comandă).

    Adaugă pentru fiecare SKU lista `in_tranzit` cu detaliul fiecărei comenzi:
    [{nr_comanda, qty, eta}], ordonată după ETA crescător. Plus `in_tranzit_qty`
    (sumă totală) și `in_tranzit_eta_min` (cea mai apropiată ETA).

    `search` filtrează pe cod_produs SAU sku (LIKE %search%)."""
    filters, params = [], {}
    if furnizor:
        filters.append("s.furnizor = :furnizor")
        params['furnizor'] = furnizor
    if gama:
        filters.append("s.gama = :gama")
        params['gama'] = gama
    if search:
        filters.append("(s.cod_produs LIKE :q OR s.cod_mare LIKE :q OR s.sku LIKE :q)")
        params['q'] = f'%{search}%'
    where = ('AND ' + ' AND '.join(filters)) if filters else ''

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
               cl.pret_achizitie_valuta                       AS pret_valuta,
               cl.moneda                                      AS moneda_valuta
        FROM stoc s
        LEFT JOIN (
            SELECT sku, SUM(cantitate) / 3.0 AS vanzari_luna_avg
            FROM tranzactii WHERE data_dl >= date('now', '-90 days')
            GROUP BY sku
        ) v ON s.sku = v.sku
        LEFT JOIN costuri_landing cl ON cl.sku = s.sku
            AND cl.an = (SELECT MAX(an) FROM costuri_landing WHERE sku = s.sku)
        WHERE s.data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
          AND s.cantitate > 0 {where}
        GROUP BY s.sku, s.furnizor, s.gama
        ORDER BY zile_stoc ASC NULLS LAST, valoare_stoc DESC
    """, params)

    # Build per-SKU in-transit detail from comenzi
    transit_by_sku = {}
    for r in query("""
        SELECT l.sku, c.nr_comanda, c.eta, c.data_estimata_livrare,
               SUM(l.cantitate_comandata) AS qty
        FROM comenzi_furnizori_linii l
        JOIN comenzi_furnizori c ON c.id = l.comanda_id
        WHERE c.status IN ('In tranzit', 'Confirmata', 'Emisa',
                           'in_tranzit', 'confirmata', 'emisa')
          AND l.cantitate_comandata > 0
        GROUP BY l.sku, c.nr_comanda, c.eta, c.data_estimata_livrare
        ORDER BY l.sku, c.eta
    """):
        transit_by_sku.setdefault(r['sku'], []).append({
            'nr_comanda': r['nr_comanda'],
            'qty':        r['qty'],
            'eta':        r['eta'] or r['data_estimata_livrare'],
        })

    for r in rows:
        orders = transit_by_sku.get(r['sku'], [])
        r['in_tranzit'] = orders
        r['in_tranzit_qty'] = sum(o['qty'] for o in orders) if orders else 0
        r['in_tranzit_eta_min'] = min((o['eta'] for o in orders if o['eta']), default=None)

    if urgenta == "critic":
        rows = [r for r in rows if r["zile_stoc"] is not None and r["zile_stoc"] < 30]
    elif urgenta == "atentie":
        rows = [r for r in rows if r["zile_stoc"] is not None and 30 <= r["zile_stoc"] < 60]
    elif urgenta == "ok":
        rows = [r for r in rows if r["zile_stoc"] is None or r["zile_stoc"] >= 60]
    return rows


def forecast_stoc_extended(furnizor=None, gama=None, urgenta=None, search=None):
    """Ca forecast_stoc_brand + avg RO/HU + sugestii de comandă per SKU."""
    filters, params = [], {}
    if furnizor:
        filters.append("s.furnizor = :furnizor")
        params['furnizor'] = furnizor
    if gama:
        filters.append("s.gama = :gama")
        params['gama'] = gama
    if search:
        filters.append("(s.cod_produs LIKE :q OR s.cod_mare LIKE :q OR s.sku LIKE :q)")
        params['q'] = f'%{search}%'
    where = ('AND ' + ' AND '.join(filters)) if filters else ''

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

    from forecast import forecast_logic

    transit_by_sku = {}
    transit_sku_meta = {}  # {sku: {'furnizor': ..., 'cod_produs': ...}}
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
        transit_by_sku.setdefault(r['sku'], []).append({
            'nr_comanda': r['nr_comanda'],
            'qty':        r['qty'],
            'eta':        r['eta'],
        })
        if r['sku'] not in transit_sku_meta:
            transit_sku_meta[r['sku']] = {
                'furnizor':   r['furnizor'],
                'cod_produs': r['cod_produs'],
            }

    lt_map = {r['furnizor']: r['zile_livrare']
              for r in query("SELECT furnizor, zile_livrare FROM termene_aprovizionare")}

    # Construiește istoricul lunar (3 ani) per furnizor, o singură interogare per brand
    furnizori_in_rows = list({r['furnizor'] for r in rows})
    monthly_cache = {}
    for f in furnizori_in_rows:
        monthly_cache[f] = forecast_logic._monthly_sales_by_sku(f)

    for r in rows:
        orders = transit_by_sku.get(r['sku'], [])
        r['in_tranzit'] = orders
        r['in_tranzit_qty'] = sum(o['qty'] for o in orders) if orders else 0
        r['in_tranzit_eta_min'] = min((o['eta'] for o in orders if o['eta']), default=None)

        lead = lt_map.get(r['furnizor'], 30)
        sku_n = forecast_logic._normalize_sku(r['sku'])
        sku_data = monthly_cache.get(r['furnizor'], {}).get(sku_n, {})

        monthly_ro = sku_data.get('ro', {})
        monthly_hu = sku_data.get('export', {})
        monthly_total = sku_data.get('total', {})

        demand_ro = forecast_logic._coverage_demand(monthly_ro, lead)
        demand_hu = forecast_logic._coverage_demand(monthly_hu, lead)

        available = float(r['stoc_total'] or 0) + float(r['in_tranzit_qty'] or 0)
        sug_ro = max(0.0, demand_ro - available)
        surplus = max(0.0, available - demand_ro)
        sug_hu = max(0.0, demand_hu - surplus)

        r['suggested_ro'] = int(round(sug_ro))
        r['suggested_hu'] = int(round(sug_hu))
        r['lead_time_days'] = lead

        # Actualizează mediile lunare cu istoricul complet (3 ani) în loc de 90 zile
        avg_total = sum(monthly_total.values()) / 12 if monthly_total else 0
        r['avg_monthly_ro'] = round(sum(monthly_ro.values()) / 12, 1) if monthly_ro else 0
        r['avg_monthly_hu'] = round(sum(monthly_hu.values()) / 12, 1) if monthly_hu else 0
        r['vanzari_luna_avg'] = round(avg_total, 1)
        if avg_total > 0:
            r['zile_stoc'] = int(float(r['stoc_total'] or 0) / (avg_total / 30))

    # Adaugă SKU-uri cu tranzit activ dar fără stoc fizic (lipsesc din tabela stoc)
    existing_skus = {r['sku'] for r in rows}
    for sku, orders in transit_by_sku.items():
        if sku in existing_skus:
            continue
        meta = transit_sku_meta.get(sku, {})
        furn = meta.get('furnizor') or ''
        if furnizor and furn != furnizor:
            continue
        if search:
            cod = meta.get('cod_produs') or ''
            if search.lower() not in sku.lower() and search.lower() not in cod.lower():
                continue

        transit_qty = sum(o['qty'] for o in orders)
        transit_eta_min = min((o['eta'] for o in orders if o['eta']), default=None)
        lead = lt_map.get(furn, 30)
        sku_n = forecast_logic._normalize_sku(sku)
        sku_data = monthly_cache.get(furn, {}).get(sku_n, {})
        if not sku_data:
            # furnizor-ul poate să nu fie în monthly_cache dacă nu era în rows
            if furn not in monthly_cache:
                monthly_cache[furn] = forecast_logic._monthly_sales_by_sku(furn)
            sku_data = monthly_cache.get(furn, {}).get(sku_n, {})
        monthly_ro = sku_data.get('ro', {})
        monthly_hu = sku_data.get('export', {})
        monthly_total = sku_data.get('total', {})
        avg_total = sum(monthly_total.values()) / 12 if monthly_total else 0

        demand_ro = forecast_logic._coverage_demand(monthly_ro, lead)
        demand_hu = forecast_logic._coverage_demand(monthly_hu, lead)
        available = float(transit_qty)
        sug_ro = max(0.0, demand_ro - available)
        surplus = max(0.0, available - demand_ro)
        sug_hu = max(0.0, demand_hu - surplus)
        zile_stoc = 0 if avg_total > 0 else None

        rows.append({
            'sku':               sku,
            'cod_produs':        meta.get('cod_produs'),
            'furnizor':          furn,
            'gama':              None,
            'stoc_total':        0,
            'valoare_stoc':      0,
            'vanzari_luna_avg':  round(avg_total, 1),
            'zile_stoc':         zile_stoc,
            'cel_mai_vechi_lot': None,
            'pret_valuta':       None,
            'moneda_valuta':     None,
            'avg_monthly_ro':    round(sum(monthly_ro.values()) / 12, 1) if monthly_ro else 0,
            'avg_monthly_hu':    round(sum(monthly_hu.values()) / 12, 1) if monthly_hu else 0,
            'in_tranzit':        orders,
            'in_tranzit_qty':    transit_qty,
            'in_tranzit_eta_min': transit_eta_min,
            'suggested_ro':      int(round(sug_ro)),
            'suggested_hu':      int(round(sug_hu)),
            'lead_time_days':    lead,
        })

    # Adaugă produse cu vânzări recente (90 zile) dar fără stoc și fără tranzit activ
    import re as _re
    existing_skus = {r['sku'] for r in rows}
    sold_no_stoc = query("""
        SELECT DISTINCT sku, furnizor,
               (SELECT MAX(s2.cod_mare) FROM stoc s2 WHERE s2.sku = tranzactii.sku) AS cod_mare
        FROM tranzactii
        WHERE data_dl >= date('now', '-90 days')
          AND sku NOT IN (
              SELECT sku FROM stoc
              WHERE data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
          )
    """)
    for row_s in sold_no_stoc:
        sku = row_s['sku']
        furn = row_s['furnizor'] or ''
        if sku in existing_skus:
            continue
        if furnizor and furn != furnizor:
            continue
        if search and search.lower() not in sku.lower():
            continue
        if furn not in monthly_cache:
            monthly_cache[furn] = forecast_logic._monthly_sales_by_sku(furn)
        sku_n = forecast_logic._normalize_sku(sku)
        sku_data = monthly_cache.get(furn, {}).get(sku_n, {})
        monthly_ro = sku_data.get('ro', {})
        monthly_hu = sku_data.get('export', {})
        monthly_total = sku_data.get('total', {})
        avg_total = sum(monthly_total.values()) / 12 if monthly_total else 0
        lead = lt_map.get(furn, 30)
        demand_ro = forecast_logic._coverage_demand(monthly_ro, lead)
        demand_hu = forecast_logic._coverage_demand(monthly_hu, lead)
        # Derivă cod furnizor din SKU dacă nu e în stoc istoric (ex: "71725" → "71725-00")
        cod_mare = row_s['cod_mare']
        if not cod_mare:
            m = _re.search(r'(\d{5,6})(?:-\d+)?$', sku.strip())
            cod_mare = (m.group(1) + '-00') if m else None
        rows.append({
            'sku':               sku,
            'cod_produs':        cod_mare,
            'furnizor':          furn,
            'gama':              None,
            'stoc_total':        0,
            'valoare_stoc':      0,
            'vanzari_luna_avg':  round(avg_total, 1),
            'zile_stoc':         0,
            'cel_mai_vechi_lot': None,
            'pret_valuta':       None,
            'moneda_valuta':     None,
            'avg_monthly_ro':    round(sum(monthly_ro.values()) / 12, 1) if monthly_ro else 0,
            'avg_monthly_hu':    round(sum(monthly_hu.values()) / 12, 1) if monthly_hu else 0,
            'in_tranzit':        [],
            'in_tranzit_qty':    0,
            'in_tranzit_eta_min': None,
            'suggested_ro':      int(round(max(0.0, demand_ro))),
            'suggested_hu':      int(round(max(0.0, demand_hu))),
            'lead_time_days':    lead,
        })
        existing_skus.add(sku)

    if urgenta == "critic":
        rows = [r for r in rows if r["zile_stoc"] is not None and r["zile_stoc"] < 30]
    elif urgenta == "atentie":
        rows = [r for r in rows if r["zile_stoc"] is not None and 30 <= r["zile_stoc"] < 60]
    elif urgenta == "ok":
        rows = [r for r in rows if r["zile_stoc"] is None or r["zile_stoc"] >= 60]
    return rows


# ── SKU → clienți cu istoric lunar ───────────────────────────────────────────


def forecast_brands_list():
    """Brands present in stock or configured in termene_aprovizionare."""
    return query("""
        SELECT DISTINCT furnizor FROM (
            SELECT furnizor FROM stoc
            WHERE data_snapshot = (SELECT MAX(data_snapshot) FROM stoc) AND cantitate > 0
            UNION
            SELECT furnizor FROM termene_aprovizionare
            UNION
            SELECT DISTINCT furnizor FROM tranzactii WHERE an >= 2024
        ) ORDER BY furnizor
    """)


# ── Raportare Basilur (grup: Basilur, KingsLeaf, Tipson) ────────────────────

BASILUR_BRANDS = ('Basilur', 'KingsLeaf', 'Tipson', 'Organsia')
_BASILUR_IN    = "('Basilur','KingsLeaf','Tipson','Organsia')"


def basilur_monthly_per_brand(an):
    """Vânzări lunare per brand Basilur-group pentru un an dat (12 luni)."""
    return query(f"""
        SELECT furnizor, luna,
            ROUND(SUM(val_neta), 0)    AS val_neta,
            ROUND(SUM(marja_bruta), 0) AS marja_bruta,
            COUNT(DISTINCT cod_client) AS nr_clienti,
            ROUND(SUM(cantitate), 0)   AS cantitate
        FROM tranzactii
        WHERE an = :an AND furnizor IN {_BASILUR_IN}
        GROUP BY furnizor, luna
        ORDER BY furnizor, luna
    """, {'an': an})


def basilur_kpi_per_brand(an, max_luna=None, luna=None):
    """KPI agregat CY vs PY per brand Basilur-group."""
    params = {'an': an, 'an_prev': an - 1}
    extra_cy = extra_py = ''
    if luna is not None:
        extra_cy = extra_py = 'AND luna = :luna'
        params['luna'] = luna
    elif max_luna is not None:
        extra_cy = extra_py = 'AND luna <= :max_luna'
        params['max_luna'] = max_luna

    return query(f"""
        WITH cy AS (
            SELECT furnizor,
                ROUND(SUM(val_neta), 0)    AS val_neta,
                ROUND(SUM(marja_bruta), 0) AS marja_bruta,
                ROUND(SUM(marja_bruta)*100.0/NULLIF(SUM(val_neta),0),1) AS marja_pct,
                COUNT(DISTINCT cod_client)  AS clienti_activi,
                COUNT(DISTINCT cod_produs)  AS nr_sku,
                COUNT(*)                    AS nr_tranzactii
            FROM tranzactii
            WHERE an = :an AND furnizor IN {_BASILUR_IN} {extra_cy}
            GROUP BY furnizor
        ),
        py AS (
            SELECT furnizor,
                ROUND(SUM(val_neta), 0) AS val_neta_py
            FROM tranzactii
            WHERE an = :an_prev AND furnizor IN {_BASILUR_IN} {extra_py}
            GROUP BY furnizor
        )
        SELECT cy.furnizor, cy.val_neta, cy.marja_bruta, cy.marja_pct,
               cy.clienti_activi, cy.nr_sku, cy.nr_tranzactii,
               COALESCE(py.val_neta_py, 0) AS val_neta_py,
               CASE WHEN COALESCE(py.val_neta_py,0) > 0
                    THEN ROUND((cy.val_neta*1.0/py.val_neta_py - 1)*100, 1)
                    ELSE NULL END AS delta_vn
        FROM cy LEFT JOIN py ON cy.furnizor = py.furnizor
        ORDER BY cy.val_neta DESC
    """, params)


def basilur_kpi_total(an, max_luna=None, luna=None):
    """KPI total grup Basilur (toate brandurile sumate)."""
    params = {'an': an, 'an_prev': an - 1}
    extra = ''
    if luna is not None:
        extra = 'AND luna = :luna'
        params['luna'] = luna
    elif max_luna is not None:
        extra = 'AND luna <= :max_luna'
        params['max_luna'] = max_luna

    return query_one(f"""
        WITH cy AS (
            SELECT ROUND(SUM(val_neta),0) AS val_neta,
                   ROUND(SUM(marja_bruta),0) AS marja_bruta,
                   ROUND(SUM(marja_bruta)*100.0/NULLIF(SUM(val_neta),0),1) AS marja_pct,
                   COUNT(DISTINCT cod_client) AS clienti_activi,
                   COUNT(DISTINCT cod_produs) AS nr_sku
            FROM tranzactii
            WHERE an = :an AND furnizor IN {_BASILUR_IN} {extra}
        ),
        py AS (
            SELECT ROUND(SUM(val_neta),0) AS val_neta_py
            FROM tranzactii
            WHERE an = :an_prev AND furnizor IN {_BASILUR_IN} {extra}
        )
        SELECT cy.val_neta, cy.marja_bruta, cy.marja_pct,
               cy.clienti_activi, cy.nr_sku,
               COALESCE(py.val_neta_py,0) AS val_neta_py,
               CASE WHEN COALESCE(py.val_neta_py,0) > 0
                    THEN ROUND((cy.val_neta*1.0/py.val_neta_py - 1)*100,1)
                    ELSE NULL END AS delta_vn
        FROM cy, py
    """, params)


def basilur_stoc_per_brand():
    """Stoc curent per brand Basilur-group la valoarea de achiziție."""
    snap = query_one("SELECT MAX(data_snapshot) AS d FROM stoc")
    snapshot = (snap or {}).get('d') if snap else None
    if not snapshot:
        return []
    return query(f"""
        SELECT furnizor,
            COUNT(DISTINCT sku)                    AS nr_sku,
            ROUND(SUM(cantitate), 0)               AS total_unitati,
            ROUND(SUM(cantitate * pret_achizitie), 0) AS valoare_achizitie
        FROM stoc
        WHERE data_snapshot = :snap
          AND furnizor IN {_BASILUR_IN}
          AND cantitate > 0
        GROUP BY furnizor
        ORDER BY valoare_achizitie DESC
    """, {'snap': snapshot})


def basilur_stoc_total():
    """Total stoc grup Basilur la valoarea de achiziție."""
    snap = query_one("SELECT MAX(data_snapshot) AS d FROM stoc")
    snapshot = (snap or {}).get('d') if snap else None
    if not snapshot:
        return {}
    return query_one(f"""
        SELECT COUNT(DISTINCT sku)                    AS nr_sku,
               ROUND(SUM(cantitate), 0)               AS total_unitati,
               ROUND(SUM(cantitate * pret_achizitie), 0) AS valoare_achizitie
        FROM stoc
        WHERE data_snapshot = :snap
          AND furnizor IN {_BASILUR_IN}
          AND cantitate > 0
    """, {'snap': snapshot}) or {}


def basilur_stoc_detail(furnizor=None):
    """Detaliu SKU stoc Basilur-group, opțional filtrat per brand."""
    snap = query_one("SELECT MAX(data_snapshot) AS d FROM stoc")
    snapshot = (snap or {}).get('d') if snap else None
    if not snapshot:
        return []
    params = {'snap': snapshot}
    extra = ''
    if furnizor:
        extra = 'AND furnizor = :furnizor'
        params['furnizor'] = furnizor
    return query(f"""
        SELECT furnizor, sku, cod_produs,
            ROUND(cantitate, 0)               AS cantitate,
            ROUND(pret_achizitie, 2)           AS pret_achizitie,
            ROUND(cantitate * pret_achizitie, 0) AS valoare_achizitie,
            nr_zile_stoc, data_intrare
        FROM stoc
        WHERE data_snapshot = :snap
          AND furnizor IN {_BASILUR_IN}
          AND cantitate > 0
          {extra}
        ORDER BY furnizor, valoare_achizitie DESC
    """, params)


def basilur_monthly_trend(years=None):
    """Trend lunar pe 3 ani per brand — pentru chart multi-an."""
    yrs = years or display_years()
    params = _years_params(yrs)
    return query(f"""
        SELECT furnizor, an, luna,
            ROUND(SUM(val_neta), 0) AS val_neta
        FROM tranzactii
        WHERE an IN (:y0,:y1,:y2) AND furnizor IN {_BASILUR_IN}
        GROUP BY furnizor, an, luna
        ORDER BY furnizor, an, luna
    """, params)


# ---------------------------------------------------------------------------
# Funcții noi: RO/HU split, in_transit, expirare, setări CRUD (Task 4)
# ---------------------------------------------------------------------------

