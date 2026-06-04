from db import query, query_one
from queries._shared import _years_params


def clients_list(an, search=None, agent=None, churn=None, brand=None, luna=None, max_luna=None, limit=500):
    conditions = ['t.an = :an']
    params = {'an': an, 'limit': limit}
    if luna is not None:
        conditions.append('t.luna = :luna')
        params['luna'] = luna
    elif max_luna is not None:
        conditions.append('t.luna <= :max_luna')
        params['max_luna'] = max_luna
    if search:
        conditions.append('t.client LIKE :search')
        params['search'] = f'%{search}%'
    if agent:
        conditions.append('t.agent = :agent_filter')
        params['agent_filter'] = agent
    if brand:
        conditions.append('t.furnizor = :brand_filter')
        params['brand_filter'] = brand
    where = ' AND '.join(conditions)
    if luna is not None:
        luna_filter_cf = 'AND luna = :luna'
        luna_filter_py = 'AND luna = :luna'
    elif max_luna is not None:
        luna_filter_cf = 'AND luna <= :max_luna'
        luna_filter_py = 'AND luna <= :max_luna'
    else:
        luna_filter_cf = ''
        luna_filter_py = ''
    rows = query(f"""
        WITH
        base_cf AS (
            SELECT cod_client, furnizor, SUM(val_neta) AS val_neta
            FROM tranzactii WHERE an = :an {luna_filter_cf} GROUP BY cod_client, furnizor
        ),
        cond_matched AS (
            SELECT b.cod_client, CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                                      WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END AS cost
            FROM base_cf b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client = b.cod_client AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.cod_client, CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                                      WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_cf b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client = b.cod_client AND c.furnizor IS NULL
            UNION ALL
            SELECT b.cod_client, CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                                      WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_cf b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client IS NULL AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.cod_client, CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                                      WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_cf b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client IS NULL AND c.furnizor IS NULL
        ),
        cond_cost AS (
            SELECT cod_client, ROUND(SUM(cost), 2) AS cost_conditii
            FROM cond_matched GROUP BY cod_client
        ),
        last_order AS (
            SELECT client, MAX(data_dl) AS ultima_comanda,
                   CAST(julianday('now') - julianday(MAX(data_dl)) AS INTEGER) AS zile_inactiv
            FROM tranzactii GROUP BY client
        ),
        prev_year AS (
            SELECT cod_client, ROUND(SUM(val_neta), 0) AS val_neta_py
            FROM tranzactii WHERE an = :an - 1 {luna_filter_py} GROUP BY cod_client
        )
        SELECT t.client, t.cod_client, t.tip_client, t.judet_client, t.agent,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE(cc.cost_conditii, 0), 0) AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(cc.cost_conditii, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)              AS marja_neta_pct,
            lo.ultima_comanda, lo.zile_inactiv,
            COUNT(DISTINCT t.furnizor) AS nr_branduri,
            CASE WHEN py.val_neta_py > 0
                 THEN ROUND((SUM(t.val_neta) / py.val_neta_py - 1) * 100, 1)
                 ELSE NULL END AS delta_vn
        FROM tranzactii t
        JOIN last_order lo ON lo.client = t.client
        LEFT JOIN cond_cost cc ON cc.cod_client = t.cod_client
        LEFT JOIN prev_year py ON py.cod_client = t.cod_client
        WHERE {where}
        GROUP BY t.client
        ORDER BY val_neta DESC
        LIMIT :limit
    """, params)
    # Python-side churn filter (derived attribute, can't use in WHERE easily)
    if churn == 'red':
        rows = [r for r in rows if (r['zile_inactiv'] or 0) >= 30]
    elif churn == 'yellow':
        rows = [r for r in rows if 16 <= (r['zile_inactiv'] or 0) <= 29]
    elif churn == 'green':
        rows = [r for r in rows if (r['zile_inactiv'] or 0) <= 15]
    return rows



def client_info(cod_client):
    return query_one("""
        SELECT client, cod_client, cui_client, tip_client,
            oras_client, judet_client, agent,
            MIN(data_dl) AS prima_comanda,
            MAX(data_dl) AS ultima_comanda,
            ROUND(SUM(val_neta), 0) AS val_neta_total,
            ROUND(SUM(marja_bruta), 0) AS marja_totala,
            COUNT(DISTINCT nr_factura) AS nr_facturi,
            COUNT(DISTINCT furnizor)   AS nr_branduri,
            CAST(julianday('now') - julianday(MAX(data_dl)) AS INTEGER) AS zile_inactiv
        FROM tranzactii
        WHERE cod_client = :cod
    """, {'cod': cod_client})


def client_orders(cod_client, limit=100):
    return query("""
        SELECT nr_factura, data_dl, sku, furnizor,
            ROUND(cantitate, 0) AS cantitate,
            ROUND(val_neta, 2)  AS val_neta,
            ROUND(marja_bruta * 100.0 / NULLIF(val_neta, 0), 1) AS marja_pct
        FROM tranzactii
        WHERE cod_client = :cod
        ORDER BY data_dl DESC, nr_factura DESC
        LIMIT :limit
    """, {'cod': cod_client, 'limit': limit})


def client_brand_mix(cod_client, an):
    return query("""
        SELECT furnizor, ROUND(SUM(val_neta), 0) AS val_neta
        FROM tranzactii
        WHERE cod_client = :cod AND an = :an
        GROUP BY furnizor
        ORDER BY val_neta DESC
    """, {'cod': cod_client, 'an': an})


def client_yearly(cod_client):
    return query("""
        SELECT an, ROUND(SUM(val_neta), 0) AS val_neta
        FROM tranzactii
        WHERE cod_client = :cod
        GROUP BY an ORDER BY an
    """, {'cod': cod_client})



def client_products_full(cod_client, an, luna=None, max_luna=None):
    """Client's products with VN, MB, MN at SKU level (proportional brand-condition allocation).
    Includes delta % vs prior year for same period (cantitate and val_neta)."""
    if luna:
        period_filter = "AND luna = :luna"
    elif max_luna:
        period_filter = "AND luna <= :max_luna"
    else:
        period_filter = ""

    sql = f"""
        WITH
        sku_vn AS (
            SELECT furnizor, sku, SUM(val_neta) AS vn_sku
            FROM tranzactii WHERE cod_client = :cod AND an = :an {period_filter}
            GROUP BY furnizor, sku
        ),
        brand_vn AS (
            SELECT furnizor, SUM(vn_sku) AS vn_brand
            FROM sku_vn GROUP BY furnizor
        ),
        cond_matched AS (
            SELECT b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.vn_brand * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END AS cost
            FROM brand_vn b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client = :cod AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.vn_brand * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM brand_vn b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client = :cod AND c.furnizor IS NULL
            UNION ALL
            SELECT b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.vn_brand * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM brand_vn b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client IS NULL AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.vn_brand * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM brand_vn b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client IS NULL AND c.furnizor IS NULL
        ),
        cond_by_brand AS (
            SELECT furnizor, ROUND(SUM(cost), 4) AS cost_conditii
            FROM cond_matched GROUP BY furnizor
        ),
        cond_per_sku AS (
            SELECT s.sku, s.furnizor,
                ROUND(COALESCE(cb.cost_conditii, 0) * s.vn_sku / NULLIF(b.vn_brand, 0), 0)
                AS cost_conditii
            FROM sku_vn s
            JOIN brand_vn b ON b.furnizor = s.furnizor
            LEFT JOIN cond_by_brand cb ON cb.furnizor = s.furnizor
        ),
        sku_py AS (
            SELECT sku, furnizor,
                SUM(cantitate) AS cantitate_py,
                SUM(val_neta)  AS val_neta_py
            FROM tranzactii
            WHERE cod_client = :cod AND an = :an - 1 {period_filter}
            GROUP BY sku, furnizor
        )
        SELECT t.sku, MIN(t.cod_produs) AS cod_produs, t.furnizor,
            ROUND(SUM(t.val_neta) / NULLIF(SUM(t.cantitate), 0), 2) AS pret_mediu,
            ROUND(SUM(t.cantitate), 0)   AS cantitate,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE(cs.cost_conditii, 0), 0)       AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(cs.cost_conditii, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct,
            ROUND((SUM(t.cantitate) - py.cantitate_py) * 100.0
                   / NULLIF(py.cantitate_py, 0), 1)                            AS delta_cant_pct,
            ROUND((SUM(t.val_neta) - py.val_neta_py) * 100.0
                   / NULLIF(py.val_neta_py, 0), 1)                             AS delta_vn_pct
        FROM tranzactii t
        LEFT JOIN cond_per_sku cs ON cs.sku = t.sku AND cs.furnizor = t.furnizor
        LEFT JOIN sku_py py ON py.sku = t.sku AND py.furnizor = t.furnizor
        WHERE t.cod_client = :cod AND t.an = :an {period_filter}
        GROUP BY t.sku, t.furnizor
        ORDER BY val_neta DESC
    """
    params = {'cod': cod_client, 'an': an}
    if luna:
        params['luna'] = luna
    elif max_luna:
        params['max_luna'] = max_luna
    return query(sql, params)


def client_yearly_full(cod_client):
    """Client's yearly summary: VN, MB, MN."""
    return query("""
        WITH cond_by_year AS (
            SELECT b.an,
                ROUND(SUM(
                    CASE WHEN c.tip_valoare='pct'      THEN b.val_neta * c.valoare / 100.0
                         WHEN c.tip_valoare='suma_fixa' THEN c.valoare
                         ELSE 0 END
                ), 0) AS cost_conditii
            FROM (
                SELECT an, cod_client, furnizor, SUM(val_neta) AS val_neta
                FROM tranzactii WHERE cod_client = :cod GROUP BY an, cod_client, furnizor
            ) b
            JOIN conditii_comerciale c ON c.an = b.an
                AND (c.cod_client = b.cod_client OR c.cod_client IS NULL)
                AND (c.furnizor   = b.furnizor   OR c.furnizor   IS NULL)
            GROUP BY b.an
        )
        SELECT t.an,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE(cy.cost_conditii, 0), 0)       AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(cy.cost_conditii, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct
        FROM tranzactii t
        LEFT JOIN cond_by_year cy ON cy.an = t.an
        WHERE t.cod_client = :cod
        GROUP BY t.an
        ORDER BY t.an
    """, {'cod': cod_client})


def client_monthly_full(cod_client):
    """Client's monthly VN + MB trend for chart."""
    params = {'cod': cod_client}
    params.update(_years_params())
    return query("""
        SELECT an, luna,
            ROUND(SUM(val_neta), 0)    AS val_neta,
            ROUND(SUM(marja_bruta), 0) AS marja_bruta
        FROM tranzactii
        WHERE cod_client = :cod AND an IN (:y0, :y1, :y2)
        GROUP BY an, luna
        ORDER BY an, luna
    """, params)


# ── Produs (SKU) detaliu ──────────────────────────────────────────────────────

