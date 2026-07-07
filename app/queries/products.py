from db import query, query_one
from queries._shared import _years_params, _COND_CTE


def products_brands(an, luna=None, max_luna=None):
    """Brand performance CY vs PY — single query (covering index idx_cov_brands)."""
    if luna is not None:
        period_filter = 'AND luna = :luna'
        params = {'an': an, 'an_py': an - 1, 'luna': luna}
    elif max_luna is not None:
        period_filter = 'AND luna <= :max_luna'
        params = {'an': an, 'an_py': an - 1, 'max_luna': max_luna}
    else:
        period_filter = ''
        params = {'an': an, 'an_py': an - 1}

    rows = query(f"""
        WITH
        base AS (
            SELECT an, furnizor, cod_client, cod_produs,
                SUM(val_neta)    AS val_neta,
                SUM(marja_bruta) AS marja_bruta
            FROM tranzactii
            WHERE an IN (:an, :an_py) {period_filter}
            GROUP BY an, furnizor, cod_client, cod_produs
        ),
        base_brand AS (
            SELECT an, furnizor,
                SUM(val_neta)              AS val_neta,
                SUM(marja_bruta)           AS marja_bruta,
                COUNT(DISTINCT cod_client) AS nr_clienti,
                COUNT(DISTINCT cod_produs) AS nr_sku
            FROM base GROUP BY an, furnizor
        ),
        cond_by_brand AS (
            SELECT b.an, b.furnizor,
                ROUND(SUM(b.val_neta * COALESCE(cr.eff_pct, 0) / 100.0
                        + COALESCE(cr.eff_fixed, 0)), 2) AS cost_conditii
            FROM base b
            LEFT JOIN cond_resolved cr
                ON cr.an = b.an AND cr.cod_client = b.cod_client AND cr.furnizor = b.furnizor
            GROUP BY b.an, b.furnizor
        )
        SELECT bb.an, bb.furnizor,
            ROUND(bb.val_neta, 0)    AS val_neta,
            ROUND(bb.marja_bruta, 0) AS marja_bruta,
            ROUND(bb.marja_bruta * 100.0 / NULLIF(bb.val_neta, 0), 1)         AS marja_pct,
            ROUND(bb.marja_bruta - COALESCE(cb.cost_conditii, 0), 0)          AS marja_neta,
            ROUND((bb.marja_bruta - COALESCE(cb.cost_conditii, 0)) * 100.0
                   / NULLIF(bb.val_neta, 0), 1)                               AS marja_neta_pct,
            bb.nr_clienti, bb.nr_sku
        FROM base_brand bb
        LEFT JOIN cond_by_brand cb ON cb.an = bb.an AND cb.furnizor = bb.furnizor
        ORDER BY bb.an DESC, val_neta DESC
    """, params)

    cy_rows = []
    py_map  = {}
    for r in rows:
        if r['an'] == an:
            cy_rows.append(dict(r))
        else:
            py_map[r['furnizor']] = r

    for row in cy_rows:
        py = py_map.get(row['furnizor'], {})
        row['val_neta_py']       = py.get('val_neta', 0)
        row['marja_pct_py']      = py.get('marja_pct', 0)
        row['marja_neta_pct_py'] = py.get('marja_neta_pct', 0)
    return cy_rows


def products_top_skus(an, furnizor=None, limit=50, search=None, luna=None, max_luna=None):
    params = {'an': an, 'limit': limit}
    extra_inner = ''
    extra_outer = ''
    if furnizor:
        extra_inner = 'AND furnizor = :furnizor'
        extra_outer = 'AND t.furnizor = :furnizor'
        params['furnizor'] = furnizor
    if luna is not None:
        extra_inner += ' AND luna = :luna'
        extra_outer += ' AND t.luna = :luna'
        params['luna'] = luna
    elif max_luna is not None:
        extra_inner += ' AND luna <= :max_luna'
        extra_outer += ' AND t.luna <= :max_luna'
        params['max_luna'] = max_luna
    if search:
        extra_outer += """ AND (CAST(t.cod_produs AS TEXT) LIKE :q
                           OR t.sku LIKE :q
                           OR EXISTS (SELECT 1 FROM v_sku_cod v
                                      WHERE v.sku = t.sku AND v.cod LIKE :q))"""
        params['q'] = f'%{search}%'
    return query(f"""
        WITH
        sku_vn AS (
            SELECT cod_client, furnizor, sku, SUM(val_neta) AS vn_sku
            FROM tranzactii WHERE an = :an {extra_inner}
            GROUP BY cod_client, furnizor, sku
        ),
        brand_vn AS (
            SELECT cod_client, furnizor, SUM(vn_sku) AS vn_brand
            FROM sku_vn GROUP BY cod_client, furnizor
        ),
        cond_matched AS (
            SELECT b.cod_client, b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.vn_brand * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END AS cost
            FROM brand_vn b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client = b.cod_client AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.cod_client, b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.vn_brand * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM brand_vn b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client = b.cod_client AND c.furnizor IS NULL
            UNION ALL
            SELECT b.cod_client, b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.vn_brand * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM brand_vn b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client IS NULL AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.cod_client, b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.vn_brand * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM brand_vn b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client IS NULL AND c.furnizor IS NULL
        ),
        cond_cb AS (
            SELECT cod_client, furnizor, ROUND(SUM(cost), 4) AS cost_conditii
            FROM cond_matched GROUP BY cod_client, furnizor
        ),
        cond_sku AS (
            SELECT s.sku, s.furnizor,
                ROUND(SUM(ccb.cost_conditii * s.vn_sku / NULLIF(b.vn_brand, 0)), 0) AS cost_conditii
            FROM sku_vn s
            JOIN brand_vn b ON b.cod_client = s.cod_client AND b.furnizor = s.furnizor
            JOIN cond_cb ccb ON ccb.cod_client = s.cod_client AND ccb.furnizor = s.furnizor
            GROUP BY s.sku, s.furnizor
        ),
        sku_py AS (
            SELECT sku, furnizor,
                SUM(cantitate) AS cantitate_py,
                SUM(val_neta)  AS val_neta_py
            FROM tranzactii WHERE an = :an - 1 {extra_inner}
            GROUP BY sku, furnizor
        )
        SELECT t.sku, t.furnizor,
            MIN(t.cod_produs) AS cod_produs,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.cantitate), 0)   AS cantitate,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE(cs.cost_conditii, 0), 0)       AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(cs.cost_conditii, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct,
            COUNT(DISTINCT t.client)     AS nr_clienti,
            ROUND((SUM(t.cantitate) - py.cantitate_py) * 100.0
                   / NULLIF(py.cantitate_py, 0), 1)                            AS delta_cant_pct,
            ROUND((SUM(t.val_neta) - py.val_neta_py) * 100.0
                   / NULLIF(py.val_neta_py, 0), 1)                             AS delta_vn_pct
        FROM tranzactii t
        LEFT JOIN cond_sku cs ON cs.sku = t.sku AND cs.furnizor = t.furnizor
        LEFT JOIN sku_py py ON py.sku = t.sku AND py.furnizor = t.furnizor
        WHERE t.an = :an {extra_outer}
        GROUP BY t.sku, t.furnizor
        ORDER BY val_neta DESC
        LIMIT :limit
    """, params)


# ── Brand deep-dive ──────────────────────────────────────────────────────────

def brand_monthly_full(furnizor):
    """Monthly VN + MB pentru un brand în ultimii 3 ani (pentru chart)."""
    params = {'furnizor': furnizor}
    params.update(_years_params())
    return query("""
        SELECT an, luna,
            ROUND(SUM(val_neta), 0)    AS val_neta,
            ROUND(SUM(marja_bruta), 0) AS marja_bruta
        FROM tranzactii
        WHERE furnizor = :furnizor AND an IN (:y0, :y1, :y2)
        GROUP BY an, luna
        ORDER BY an, luna
    """, params)


def brand_kpi(furnizor, an, max_luna=None, luna=None):
    """KPI agregat pentru un brand: VN, MB, MN, # clienți, # SKU, vs an precedent (YTD)."""
    params = {'an': an, 'furnizor': furnizor}
    luna_filter = ''
    if luna is not None:
        luna_filter = 'AND luna = :luna'
        params['luna'] = luna
    elif max_luna is not None:
        luna_filter = 'AND luna <= :max_luna'
        params['max_luna'] = max_luna
    return query_one(f"""
        WITH
        base_cf AS (
            SELECT cod_client, SUM(val_neta) AS val_neta
            FROM tranzactii
            WHERE furnizor = :furnizor AND an = :an {luna_filter}
            GROUP BY cod_client
        ),
        cond_total AS (
            SELECT SUM(b.val_neta * COALESCE(cr.eff_pct, 0) / 100.0
                     + COALESCE(cr.eff_fixed, 0)) AS cost_conditii
            FROM base_cf b
            LEFT JOIN cond_resolved cr
                ON cr.an = :an
               AND cr.cod_client = b.cod_client
               AND cr.furnizor   = :furnizor
        )
        SELECT
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE((SELECT cost_conditii FROM cond_total), 0), 0) AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE((SELECT cost_conditii FROM cond_total), 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_neta_pct,
            COUNT(DISTINCT t.cod_client) AS nr_clienti,
            COUNT(DISTINCT t.cod_produs) AS nr_sku,
            COUNT(*)                     AS nr_tranzactii
        FROM tranzactii t
        WHERE t.furnizor = :furnizor AND t.an = :an {luna_filter}
    """, params)


def brand_clients(furnizor, an, max_luna=None, luna=None, limit=200):
    """Clienții care cumpără un brand: VN, pondere %, vs an precedent (YTD)."""
    params = {'cy': an, 'py': an - 1, 'furnizor': furnizor, 'limit': limit}
    luna_cy = ''
    luna_py = ''
    if luna is not None:
        luna_cy = 'AND luna = :luna'
        luna_py = 'AND luna = :luna'
        params['luna'] = luna
    elif max_luna is not None:
        luna_cy = 'AND luna <= :max_luna'
        luna_py = 'AND luna <= :max_luna'
        params['max_luna'] = max_luna

    rows = query(f"""
        SELECT cod_client, MAX(client) AS client, MAX(agent) AS agent,
               ROUND(SUM(val_neta), 0)    AS val_neta,
               ROUND(SUM(marja_bruta), 0) AS marja_bruta,
               ROUND(SUM(marja_bruta) * 100.0 / NULLIF(SUM(val_neta), 0), 1) AS marja_pct,
               COUNT(DISTINCT cod_produs) AS nr_sku,
               MAX(data_dl) AS ultima_livrare
        FROM tranzactii
        WHERE furnizor = :furnizor AND an = :cy {luna_cy}
        GROUP BY cod_client
        ORDER BY val_neta DESC
        LIMIT :limit
    """, params)

    rows_py = query(f"""
        SELECT cod_client, ROUND(SUM(val_neta), 0) AS val_neta_py
        FROM tranzactii
        WHERE furnizor = :furnizor AND an = :py {luna_py}
        GROUP BY cod_client
    """, params)
    py_map = {r['cod_client']: r['val_neta_py'] for r in rows_py}

    total_vn = sum((r['val_neta'] or 0) for r in rows) or 1
    for r in rows:
        r['pondere'] = round((r['val_neta'] or 0) * 100.0 / total_vn, 2)
        r['val_neta_py'] = py_map.get(r['cod_client'], 0) or 0
        if r['val_neta_py']:
            r['delta_pct'] = round((r['val_neta'] - r['val_neta_py']) / r['val_neta_py'] * 100, 1)
        else:
            r['delta_pct'] = None
    return rows



def product_kpi(sku, an, luna=None, max_luna=None):
    """KPI card for a single SKU in a given year/period (proportional condition attribution)."""
    if luna:
        period_filter = "AND luna = :luna"
    elif max_luna:
        period_filter = "AND luna <= :max_luna"
    else:
        period_filter = ""

    sql = f"""
        WITH
        base_cf AS (
            SELECT cod_client, furnizor, SUM(val_neta) AS val_neta
            FROM tranzactii WHERE sku = :sku AND an = :an {period_filter}
            GROUP BY cod_client, furnizor
        ),
        cond_matched AS (
            SELECT CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                        WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END AS cost
            FROM base_cf b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client = b.cod_client AND c.furnizor = b.furnizor
            UNION ALL
            SELECT CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                        WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_cf b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client = b.cod_client AND c.furnizor IS NULL
            UNION ALL
            SELECT CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                        WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_cf b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client IS NULL AND c.furnizor = b.furnizor
            UNION ALL
            SELECT CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                        WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_cf b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client IS NULL AND c.furnizor IS NULL
        ),
        cond_for_sku AS (
            SELECT ROUND(SUM(cost), 0) AS total_cost FROM cond_matched
        )
        SELECT t.sku, t.furnizor,
            (SELECT cod FROM v_sku_cod WHERE v_sku_cod.sku = t.sku) AS cod_produs,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.cantitate), 0)   AS cantitate,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE((SELECT total_cost FROM cond_for_sku), 0), 0)
                AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE((SELECT total_cost FROM cond_for_sku), 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct,
            COUNT(DISTINCT t.client) AS nr_clienti,
            COUNT(DISTINCT t.agent)  AS nr_agenti,
            MAX(t.data_dl)           AS ultima_vanzare
        FROM tranzactii t
        WHERE t.sku = :sku AND t.an = :an {period_filter}
    """
    params = {'sku': sku, 'an': an}
    if luna:
        params['luna'] = luna
    elif max_luna:
        params['max_luna'] = max_luna
    return query_one(sql, params)


def product_clients(sku, an, luna=None, max_luna=None):
    """Clients buying this SKU with MB + MN + delta % vs prior year same period."""
    if luna:
        period_filter = "AND luna = :luna"
    elif max_luna:
        period_filter = "AND luna <= :max_luna"
    else:
        period_filter = ""

    cond_cte = _COND_CTE.format(where_inner=f"sku = :sku AND an = :an {period_filter}")
    sql = f"""
        WITH {cond_cte},
        client_py AS (
            SELECT cod_client,
                SUM(cantitate) AS cantitate_py,
                SUM(val_neta)  AS val_neta_py
            FROM tranzactii
            WHERE sku = :sku AND an = :an - 1 {period_filter}
            GROUP BY cod_client
        )
        SELECT t.client, t.cod_client, t.agent,
            ROUND(SUM(t.cantitate), 0)   AS cantitate,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE(cc.cost_conditii, 0), 0)  AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(cc.cost_conditii, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct,
            ROUND((SUM(t.cantitate) - py.cantitate_py) * 100.0
                   / NULLIF(py.cantitate_py, 0), 1)                            AS delta_cant_pct,
            ROUND((SUM(t.val_neta) - py.val_neta_py) * 100.0
                   / NULLIF(py.val_neta_py, 0), 1)                             AS delta_vn_pct
        FROM tranzactii t
        LEFT JOIN cond_cost cc ON cc.cod_client = t.cod_client
        LEFT JOIN client_py py ON py.cod_client = t.cod_client
        WHERE t.sku = :sku AND t.an = :an {period_filter}
        GROUP BY t.client
        ORDER BY val_neta DESC
    """
    params = {'sku': sku, 'an': an}
    if luna:
        params['luna'] = luna
    elif max_luna:
        params['max_luna'] = max_luna
    return query(sql, params)


def product_clients_istoric(sku):
    """All clients that ever bought this SKU: Val Netă pivot per year + totals.
    Membership is all-time, so historic buyers stay visible even when the
    period view (product_clients) has no rows for them.
    Returns (rows, years) — years drive the dynamic columns in the template."""
    raw = query("""
        SELECT t.client, t.cod_client, MAX(t.agent) AS agent, t.an,
            ROUND(SUM(t.cantitate), 0) AS cantitate,
            ROUND(SUM(t.val_neta), 0)  AS val_neta,
            MAX(t.data_dl)             AS ultima_achizitie
        FROM tranzactii t
        WHERE t.sku = :sku
        GROUP BY t.client, t.an
    """, {'sku': sku})
    years = sorted({r['an'] for r in raw})
    clients = {}
    for r in raw:
        c = clients.setdefault(r['client'], {
            'client': r['client'], 'cod_client': r['cod_client'], 'agent': r['agent'],
            'per_an': {}, 'cantitate': 0, 'val_neta': 0, 'ultima_achizitie': None,
        })
        c['per_an'][r['an']] = r['val_neta'] or 0
        c['cantitate'] += r['cantitate'] or 0
        c['val_neta'] += r['val_neta'] or 0
        if not c['ultima_achizitie'] or (r['ultima_achizitie'] or '') > c['ultima_achizitie']:
            c['ultima_achizitie'] = r['ultima_achizitie']
            c['agent'] = r['agent']
    rows = sorted(clients.values(), key=lambda c: c['val_neta'], reverse=True)
    return rows, years


def product_monthly(sku):
    """Monthly trend for a SKU across last 3 years."""
    params = {'sku': sku}
    params.update(_years_params())
    return query("""
        SELECT an, luna,
            ROUND(SUM(val_neta), 0)  AS val_neta,
            ROUND(SUM(cantitate), 0) AS cantitate
        FROM tranzactii
        WHERE sku = :sku AND an IN (:y0, :y1, :y2)
        GROUP BY an, luna
        ORDER BY an, luna
    """, params)


def product_yearly(sku):
    """Yearly VN + MB + MN trend for a SKU."""
    return query("""
        WITH
        base_acf AS (
            SELECT an, cod_client, furnizor, SUM(val_neta) AS val_neta
            FROM tranzactii WHERE sku = :sku GROUP BY an, cod_client, furnizor
        ),
        cond_matched AS (
            SELECT b.an, CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                              WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END AS cost
            FROM base_acf b JOIN conditii_comerciale c
                ON c.an = b.an AND c.cod_client = b.cod_client AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.an, CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                              WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_acf b JOIN conditii_comerciale c
                ON c.an = b.an AND c.cod_client = b.cod_client AND c.furnizor IS NULL
            UNION ALL
            SELECT b.an, CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                              WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_acf b JOIN conditii_comerciale c
                ON c.an = b.an AND c.cod_client IS NULL AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.an, CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                              WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_acf b JOIN conditii_comerciale c
                ON c.an = b.an AND c.cod_client IS NULL AND c.furnizor IS NULL
        ),
        cond_per_year AS (
            SELECT an, ROUND(SUM(cost), 0) AS total_cost
            FROM cond_matched GROUP BY an
        )
        SELECT t.an,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.cantitate), 0)   AS cantitate,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE(cy.total_cost, 0), 0)          AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(cy.total_cost, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct,
            COUNT(DISTINCT t.client) AS nr_clienti
        FROM tranzactii t
        LEFT JOIN cond_per_year cy ON cy.an = t.an
        WHERE t.sku = :sku
        GROUP BY t.an
        ORDER BY t.an
    """, {'sku': sku})


# ── Profitabilitate — ranking și matrice ─────────────────────────────────────


def sku_clients_monthly(sku: str) -> list:
    """
    Returns per-client monthly qty for a SKU across all years.
    Shape: [{client, cod_client, years: {year: [12 values]}, total_qty}]
    """
    rows = query("""
        SELECT client, cod_client, an, luna, SUM(cantitate) AS qty
        FROM tranzactii
        WHERE sku = :sku
        GROUP BY client, cod_client, an, luna
        ORDER BY an DESC, luna
    """, {'sku': sku})

    by_client = {}
    for r in rows:
        cl = r['client']
        if cl not in by_client:
            by_client[cl] = {'cod_client': r['cod_client'], 'years': {}}
        yr = str(r['an'])
        if yr not in by_client[cl]['years']:
            by_client[cl]['years'][yr] = [0] * 12
        by_client[cl]['years'][yr][int(r['luna']) - 1] = r['qty'] or 0

    result = []
    for client, data in by_client.items():
        total = sum(sum(v) for v in data['years'].values())
        result.append({
            'client': client,
            'cod_client': data['cod_client'],
            'years': data['years'],
            'total_qty': total,
        })
    result.sort(key=lambda x: -x['total_qty'])
    return result


# ── Termene aprovizionare ─────────────────────────────────────────────────────

