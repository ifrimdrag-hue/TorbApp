import datetime
from db import query, query_one
from queries._shared import _years_params, current_year, prior_year, _COND_CTE


def kpi_cards():
    """YTD totals for current and prior year (same calendar period).
    Folosește cond_resolved pentru cost_conditii."""
    today = datetime.date.today()
    same_day_py = today.replace(year=today.year - 1)
    return query("""
        WITH base AS (
            SELECT an, cod_client, furnizor, client, val_neta, marja_bruta
            FROM tranzactii
            WHERE (an = :cy AND data_dl <= :today)
               OR (an = :py AND data_dl <= :same_day_py)
        ),
        base_cfb AS (
            SELECT an, cod_client, furnizor, SUM(val_neta) AS val_neta
            FROM base GROUP BY an, cod_client, furnizor
        ),
        cond_by_year AS (
            SELECT b.an,
                ROUND(SUM(b.val_neta * COALESCE(cr.eff_pct, 0) / 100.0
                        + COALESCE(cr.eff_fixed, 0)), 2) AS cost_conditii
            FROM base_cfb b
            LEFT JOIN cond_resolved cr
                ON cr.an = b.an
               AND cr.cod_client = b.cod_client
               AND cr.furnizor   = b.furnizor
            GROUP BY b.an
        )
        SELECT
            b.an,
            ROUND(SUM(b.val_neta), 0)    AS val_neta,
            ROUND(SUM(b.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(b.marja_bruta) * 100.0 / NULLIF(SUM(b.val_neta), 0), 1) AS marja_pct,
            ROUND(SUM(b.marja_bruta) - COALESCE(cy.cost_conditii, 0), 0) AS marja_neta,
            COUNT(DISTINCT b.client) AS clienti_activi
        FROM base b
        LEFT JOIN cond_by_year cy ON cy.an = b.an
        GROUP BY b.an
        ORDER BY b.an DESC
    """, {
        'cy': today.year, 'py': today.year - 1,
        'today': today.isoformat(),
        'same_day_py': same_day_py.isoformat(),
    })


def kpi_luna_curenta():
    """Vânzări nete luna curentă (parțial, până azi) vs aceeași lună completă an precedent."""
    today = datetime.date.today()
    cy = today.year
    py = cy - 1
    luna = today.month
    rows = query("""
        SELECT an, ROUND(SUM(val_neta), 0) AS val_neta
        FROM tranzactii
        WHERE luna = :luna
          AND an IN (:cy, :py)
          AND (an != :cy OR data_dl <= :today)
        GROUP BY an
    """, {'cy': cy, 'py': py, 'luna': luna, 'today': today.isoformat()})
    by_year = {r['an']: r['val_neta'] or 0 for r in rows}
    return {
        'vn_cy': by_year.get(cy, 0),
        'vn_py': by_year.get(py, 0),
        'luna_nr': luna,
    }


def monthly_trend():
    return query("""
        SELECT an, luna, ROUND(SUM(val_neta), 0) AS val_neta
        FROM tranzactii
        WHERE an IN (:y0, :y1, :y2)
        GROUP BY an, luna
        ORDER BY an, luna
    """, _years_params())


def brand_mix(an):
    return query("""
        SELECT furnizor, ROUND(SUM(val_neta), 0) AS val_neta
        FROM tranzactii WHERE an = :an
        GROUP BY furnizor
        ORDER BY val_neta DESC
    """, {'an': an})


def channel_mix(an):
    return query("""
        SELECT agent, ROUND(SUM(val_neta), 0) AS val_neta
        FROM tranzactii WHERE an = :an
        GROUP BY agent
        ORDER BY val_neta DESC
    """, {'an': an})


def risk_kaufland(an):
    row = query_one("""
        SELECT ROUND(
            SUM(CASE WHEN client LIKE '%KAUFLAND%' THEN val_neta ELSE 0 END) * 100.0
            / NULLIF(SUM(val_neta), 0), 1) AS pct
        FROM tranzactii WHERE an = :an
    """, {'an': an})
    return row['pct'] if row else 0


def risk_agent(an, agent_name):
    row = query_one("""
        SELECT ROUND(
            SUM(CASE WHEN agent = :agent THEN val_neta ELSE 0 END) * 100.0
            / NULLIF(SUM(val_neta), 0), 1) AS pct
        FROM tranzactii WHERE an = :an
    """, {'an': an, 'agent': agent_name})
    return row['pct'] if row else 0


def churn_clients(days=60):
    return query("""
        SELECT client, agent, MAX(data_dl) AS ultima_comanda,
               CAST(julianday('now') - julianday(MAX(data_dl)) AS INTEGER) AS zile_inactiv
        FROM tranzactii
        GROUP BY client
        HAVING zile_inactiv > :days
        ORDER BY zile_inactiv DESC
    """, {'days': days})


def top_clients(an, limit=10):
    return query("""
        WITH
        base_cf AS (
            SELECT cod_client, furnizor, SUM(val_neta) AS val_neta
            FROM tranzactii WHERE an = :an GROUP BY cod_client, furnizor
        ),
        cond_cost AS (
            SELECT b.cod_client,
                ROUND(SUM(b.val_neta * COALESCE(cr.eff_pct, 0) / 100.0
                        + COALESCE(cr.eff_fixed, 0)), 2) AS cost_conditii
            FROM base_cf b
            LEFT JOIN cond_resolved cr
                ON cr.an = :an
               AND cr.cod_client = b.cod_client
               AND cr.furnizor   = b.furnizor
            GROUP BY b.cod_client
        )
        SELECT t.client, t.cod_client, t.agent,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE(cc.cost_conditii, 0), 0) AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(cc.cost_conditii, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)              AS marja_neta_pct,
            MAX(t.data_dl) AS ultima_comanda
        FROM tranzactii t
        LEFT JOIN cond_cost cc ON cc.cod_client = t.cod_client
        WHERE t.an = :an
        GROUP BY t.client
        ORDER BY val_neta DESC
        LIMIT :limit
    """, {'an': an, 'limit': limit})




def team_table(an, max_luna=None, luna=None):
    """Folosește cond_resolved (materializat) pentru cost_conditii."""
    params = {'an': an}
    luna_filter = ''
    luna_filter_t = ''
    if luna is not None:
        luna_filter = 'AND luna = :luna'
        luna_filter_t = 'AND t.luna = :luna'
        params['luna'] = luna
    elif max_luna is not None:
        luna_filter = 'AND luna <= :max_luna'
        luna_filter_t = 'AND t.luna <= :max_luna'
        params['max_luna'] = max_luna
    return query(f"""
        WITH
        base_acf AS (
            SELECT agent, cod_client, furnizor, SUM(val_neta) AS val_neta
            FROM tranzactii WHERE an = :an {luna_filter}
            GROUP BY agent, cod_client, furnizor
        ),
        cond_by_agent AS (
            SELECT b.agent,
                ROUND(SUM(b.val_neta * COALESCE(cr.eff_pct, 0) / 100.0
                        + COALESCE(cr.eff_fixed, 0)), 2) AS cost_conditii
            FROM base_acf b
            LEFT JOIN cond_resolved cr
                ON cr.an = :an
               AND cr.cod_client = b.cod_client
               AND cr.furnizor   = b.furnizor
            GROUP BY b.agent
        )
        SELECT t.agent,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE(ca.cost_conditii, 0), 0) AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(ca.cost_conditii, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)              AS marja_neta_pct,
            COUNT(DISTINCT t.client)     AS clienti_activi,
            MAX(t.data_dl)               AS ultima_livrare
        FROM tranzactii t
        LEFT JOIN cond_by_agent ca ON ca.agent = t.agent
        WHERE t.an = :an {luna_filter_t}
        GROUP BY t.agent
        ORDER BY val_neta DESC
    """, params)


def agent_kpi(agent, an, max_luna=None, luna=None):
    """KPI agent. Cu max_luna setat, comparatia devine YTD apples-to-apples."""
    params = {'agent': agent, 'an': an}
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
            SELECT cod_client, furnizor, SUM(val_neta) AS val_neta
            FROM tranzactii WHERE agent = :agent AND an = :an {luna_filter}
            GROUP BY cod_client, furnizor
        ),
        cond_cost AS (
            SELECT ROUND(SUM(b.val_neta * COALESCE(cr.eff_pct, 0) / 100.0
                          + COALESCE(cr.eff_fixed, 0)), 2) AS cost_conditii
            FROM base_cf b
            LEFT JOIN cond_resolved cr
                ON cr.an = :an
               AND cr.cod_client = b.cod_client
               AND cr.furnizor   = b.furnizor
        )
        SELECT agent,
            ROUND(SUM(val_neta), 0)    AS val_neta,
            ROUND(SUM(marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(marja_bruta) * 100.0 / NULLIF(SUM(val_neta), 0), 1) AS marja_pct,
            ROUND(SUM(marja_bruta) - COALESCE((SELECT cost_conditii FROM cond_cost), 0), 0) AS marja_neta,
            COUNT(DISTINCT client)     AS clienti_activi,
            COUNT(DISTINCT nr_factura) AS nr_facturi,
            ROUND(SUM(val_neta) / NULLIF(COUNT(DISTINCT nr_factura), 0), 0) AS avg_comanda,
            MAX(data_dl)               AS ultima_livrare
        FROM tranzactii
        WHERE agent = :agent AND an = :an {luna_filter}
    """, params)


def agent_monthly_trend(agent):
    return query("""
        SELECT an, luna, ROUND(SUM(val_neta), 0) AS val_neta
        FROM tranzactii
        WHERE agent = :agent AND an IN (:py, :cy)
        GROUP BY an, luna
        ORDER BY an, luna
    """, {'agent': agent, 'py': prior_year(), 'cy': current_year()})


def agent_clients(agent, an):
    return query("""
        WITH last_order AS (
            SELECT client, MAX(data_dl) AS ultima_comanda,
                   CAST(julianday('now') - julianday(MAX(data_dl)) AS INTEGER) AS zile_inactiv
            FROM tranzactii GROUP BY client
        )
        SELECT t.client, t.cod_client,
            ROUND(SUM(t.val_neta), 0) AS val_neta,
            lo.ultima_comanda, lo.zile_inactiv
        FROM tranzactii t
        JOIN last_order lo ON lo.client = t.client
        WHERE t.agent = :agent AND t.an = :an
        GROUP BY t.client
        ORDER BY val_neta DESC
    """, {'agent': agent, 'an': an})


def agent_top_skus(agent, an, limit=10):
    return query("""
        SELECT sku, furnizor,
            ROUND(SUM(val_neta), 0) AS val_neta,
            ROUND(SUM(cantitate), 0) AS cantitate,
            ROUND(SUM(marja_bruta) * 100.0 / NULLIF(SUM(val_neta), 0), 1) AS marja_pct
        FROM tranzactii
        WHERE agent = :agent AND an = :an
        GROUP BY sku, furnizor
        ORDER BY val_neta DESC
        LIMIT :limit
    """, {'agent': agent, 'an': an, 'limit': limit})


def agent_monthly_base(agent_name: str, an: int = None):
    """Monthly Sales + Margin for an agent in a given year (base for simulator).

    Default `an` = anul precedent (baseline simulator)."""
    if an is None:
        an = prior_year()
    return query("""
        SELECT luna,
               ROUND(SUM(val_neta), 0)     AS val_neta,
               ROUND(SUM(marja_bruta), 0)  AS marja_bruta
        FROM tranzactii
        WHERE agent = :agent AND an = :an
        GROUP BY luna
        ORDER BY luna
    """, {"agent": agent_name, "an": an})


def agent_monthly_all_years(agent_name: str):
    """Monthly Sales + Margin for agent in prior_year + current_year."""
    return query("""
        SELECT an, luna,
               ROUND(SUM(val_neta), 0)    AS val_neta,
               ROUND(SUM(marja_bruta), 0) AS marja_bruta
        FROM tranzactii
        WHERE agent = :agent AND an IN (:py, :cy)
        GROUP BY an, luna
        ORDER BY an, luna
    """, {"agent": agent_name, "py": prior_year(), "cy": current_year()})


def agent_brand_monthly(agent_name: str, an: int):
    """Monthly Sales per strategic brand for an agent."""
    return query("""
        SELECT luna, furnizor,
               ROUND(SUM(val_neta), 0) AS val_neta
        FROM tranzactii
        WHERE agent = :agent AND an = :an
          AND furnizor IN ('Basilur', 'Delaviuda', 'Leonex', 'Celmar', 'Toras')
        GROUP BY luna, furnizor
        ORDER BY luna, furnizor
    """, {"agent": agent_name, "an": an})




def agent_clients_full(agent, an, luna=None, max_luna=None):
    """Agent's clients: VN, MB (RON+%), MN (RON+%), YoY comparison, days inactive."""
    today = datetime.date.today()
    same_day_py = today.replace(year=today.year - 1)

    if luna is not None:
        period_filter = 'AND luna = :luna'
        params_cy = {'agent': agent, 'an': an, 'luna': luna}
        params_py = {'agent': agent, 'an': an - 1, 'luna': luna}
    elif max_luna is not None:
        period_filter = 'AND luna <= :max_luna'
        params_cy = {'agent': agent, 'an': an, 'max_luna': max_luna}
        params_py = {'agent': agent, 'an': an - 1, 'max_luna': max_luna}
    else:
        period_filter = 'AND data_dl <= :cutoff'
        params_cy = {'agent': agent, 'an': an, 'cutoff': today.isoformat()}
        params_py = {'agent': agent, 'an': an - 1, 'cutoff': same_day_py.isoformat()}

    cond_cte = _COND_CTE.format(where_inner=f"agent = :agent AND an = :an {period_filter}")
    rows_cy = query(f"""
        WITH
        {cond_cte},
        last_order AS (
            SELECT client, MAX(data_dl) AS ultima_comanda,
                   CAST(julianday('now') - julianday(MAX(data_dl)) AS INTEGER) AS zile_inactiv
            FROM tranzactii GROUP BY client
        )
        SELECT t.client, t.cod_client,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE(cc.cost_conditii, 0), 0)       AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(cc.cost_conditii, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct,
            lo.ultima_comanda, lo.zile_inactiv
        FROM tranzactii t
        LEFT JOIN cond_cost cc ON cc.cod_client = t.cod_client
        JOIN last_order lo ON lo.client = t.client
        WHERE t.agent = :agent AND t.an = :an {period_filter}
        GROUP BY t.client
        ORDER BY val_neta DESC
    """, params_cy)

    cond_cte_py = _COND_CTE.format(where_inner=f"agent = :agent AND an = :an {period_filter}")
    rows_py = query(f"""
        WITH {cond_cte_py}
        SELECT t.client,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.marja_bruta) - COALESCE(cc.cost_conditii, 0), 0) AS marja_neta
        FROM tranzactii t
        LEFT JOIN cond_cost cc ON cc.cod_client = t.cod_client
        WHERE t.agent = :agent AND t.an = :an {period_filter}
        GROUP BY t.client
    """, params_py)

    py_map = {r['client']: r for r in rows_py}
    for row in rows_cy:
        py = py_map.get(row['client'], {})
        row['val_neta_py'] = py.get('val_neta', 0) or 0
        py_mn = py.get('marja_neta') or 0
        cy_mn = row.get('marja_neta') or 0
        row['delta_mn_pct'] = round((cy_mn / py_mn - 1) * 100, 1) if py_mn else None
    return rows_cy


def agent_brands_full(agent, an, luna=None, max_luna=None):
    """Brand breakdown for an agent with MB + MN."""
    if luna is not None:
        period_filter = 'AND luna = :luna'
        params = {'agent': agent, 'an': an, 'luna': luna}
    elif max_luna is not None:
        period_filter = 'AND luna <= :max_luna'
        params = {'agent': agent, 'an': an, 'max_luna': max_luna}
    else:
        period_filter = ''
        params = {'agent': agent, 'an': an}

    return query(f"""
        WITH
        base_fc AS (
            SELECT furnizor, cod_client, SUM(val_neta) AS val_neta
            FROM tranzactii WHERE agent = :agent AND an = :an {period_filter}
            GROUP BY furnizor, cod_client
        ),
        cond_matched AS (
            SELECT b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END AS cost
            FROM base_fc b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client = b.cod_client AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_fc b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client = b.cod_client AND c.furnizor IS NULL
            UNION ALL
            SELECT b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_fc b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client IS NULL AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.furnizor,
                CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_fc b JOIN conditii_comerciale c
                ON c.an = :an AND c.cod_client IS NULL AND c.furnizor IS NULL
        ),
        cond_by_brand AS (
            SELECT furnizor, ROUND(SUM(cost), 2) AS cost_conditii
            FROM cond_matched GROUP BY furnizor
        )
        SELECT t.furnizor,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE(cb.cost_conditii, 0), 0)       AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(cb.cost_conditii, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct,
            COUNT(DISTINCT t.client) AS nr_clienti
        FROM tranzactii t
        LEFT JOIN cond_by_brand cb ON cb.furnizor = t.furnizor
        WHERE t.agent = :agent AND t.an = :an {period_filter}
        GROUP BY t.furnizor
        ORDER BY val_neta DESC
    """, params)


def agent_skus_full(agent, an, limit=None, luna=None, max_luna=None):
    """All SKUs for an agent with MB + MN (proportional condition attribution).
    `limit=None` ⇒ fără limită (default după ce userul a cerut tot istoricul)."""
    limit_clause = "" if limit is None else "LIMIT :limit"
    if luna is not None:
        period_filter = "AND luna = :luna"
        params = {'agent': agent, 'an': an, 'luna': luna}
    elif max_luna is not None:
        period_filter = "AND luna <= :max_luna"
        params = {'agent': agent, 'an': an, 'max_luna': max_luna}
    else:
        period_filter = ""
        params = {'agent': agent, 'an': an}
    if limit is not None:
        params['limit'] = limit
    return query(f"""
        WITH
        sku_vn AS (
            SELECT cod_client, furnizor, sku, SUM(val_neta) AS vn_sku
            FROM tranzactii WHERE agent = :agent AND an = :an {period_filter}
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
            FROM tranzactii
            WHERE agent = :agent AND an = :an - 1 {period_filter}
            GROUP BY sku, furnizor
        )
        SELECT t.sku, t.furnizor,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.cantitate), 0)   AS cantitate,
            ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
            ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
            ROUND(SUM(t.marja_bruta) - COALESCE(cs.cost_conditii, 0), 0)       AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(cs.cost_conditii, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct,
            COUNT(DISTINCT t.client) AS nr_clienti,
            ROUND((SUM(t.cantitate) - py.cantitate_py) * 100.0 / NULLIF(py.cantitate_py, 0), 1) AS delta_cant_pct,
            ROUND((SUM(t.val_neta)  - py.val_neta_py)  * 100.0 / NULLIF(py.val_neta_py,  0), 1) AS delta_vn_pct
        FROM tranzactii t
        LEFT JOIN cond_sku cs ON cs.sku = t.sku AND cs.furnizor = t.furnizor
        LEFT JOIN sku_py py   ON py.sku  = t.sku AND py.furnizor = t.furnizor
        WHERE t.agent = :agent AND t.an = :an {period_filter}
        GROUP BY t.sku, t.furnizor
        ORDER BY val_neta DESC
        {limit_clause}
    """, params)


def agent_brand_sku_monthly(agent, an):
    """Pivot CY+PY per (brand, sku, luna): val_neta + cantitate."""
    rows = query("""
        SELECT an, luna, furnizor, sku,
               SUM(val_neta)  AS vn,
               SUM(cantitate) AS qty
        FROM tranzactii
        WHERE agent = :agent AND an IN (:cy, :py)
        GROUP BY an, luna, furnizor, sku
    """, {'agent': agent, 'cy': an, 'py': an - 1})

    # Structură:
    # {brand: {
    #    'cy_vn': [12], 'py_vn': [12], 'cy_qty': [12], 'py_qty': [12],
    #    'skus': {sku: {'cy_vn': [12], 'py_vn': [12], 'cy_qty': [12], 'py_qty': [12]}}
    # }}
    out = {}
    for r in rows:
        brand = r['furnizor'] or 'Altele'
        sku   = r['sku']      or '—'
        m_idx = (int(r['luna']) - 1) if r['luna'] else 0
        is_cy = r['an'] == an

        if brand not in out:
            out[brand] = {
                'cy_vn': [0]*12, 'py_vn': [0]*12,
                'cy_qty':[0]*12, 'py_qty':[0]*12,
                'skus':  {},
            }
        if sku not in out[brand]['skus']:
            out[brand]['skus'][sku] = {
                'cy_vn': [0]*12, 'py_vn': [0]*12,
                'cy_qty':[0]*12, 'py_qty':[0]*12,
            }

        bd = out[brand]
        sd = out[brand]['skus'][sku]
        vn  = r['vn']  or 0
        qty = r['qty'] or 0
        if is_cy:
            bd['cy_vn'][m_idx]  += vn
            bd['cy_qty'][m_idx] += qty
            sd['cy_vn'][m_idx]  += vn
            sd['cy_qty'][m_idx] += qty
        else:
            bd['py_vn'][m_idx]  += vn
            bd['py_qty'][m_idx] += qty
            sd['py_vn'][m_idx]  += vn
            sd['py_qty'][m_idx] += qty
    return out


def agent_monthly_full(agent):
    """Monthly VN + MB + MN for last 3 years (trend charts)."""
    params = {'agent': agent}
    params.update(_years_params())
    return query("""
        WITH
        base AS (
            SELECT an, luna,
                ROUND(SUM(val_neta), 0)    AS val_neta,
                ROUND(SUM(marja_bruta), 0) AS marja_bruta
            FROM tranzactii
            WHERE agent = :agent AND an IN (:y0, :y1, :y2)
            GROUP BY an, luna
        ),
        base_alcf AS (
            SELECT an, luna, cod_client, furnizor, SUM(val_neta) AS val_neta
            FROM tranzactii WHERE agent = :agent AND an IN (:y0, :y1, :y2)
            GROUP BY an, luna, cod_client, furnizor
        ),
        cond_matched AS (
            SELECT b.an, b.luna,
                CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END AS cost
            FROM base_alcf b JOIN conditii_comerciale c
                ON c.an = b.an AND c.cod_client = b.cod_client AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.an, b.luna,
                CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_alcf b JOIN conditii_comerciale c
                ON c.an = b.an AND c.cod_client = b.cod_client AND c.furnizor IS NULL
            UNION ALL
            SELECT b.an, b.luna,
                CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_alcf b JOIN conditii_comerciale c
                ON c.an = b.an AND c.cod_client IS NULL AND c.furnizor = b.furnizor
            UNION ALL
            SELECT b.an, b.luna,
                CASE WHEN c.tip_valoare='pct' THEN b.val_neta * c.valoare / 100.0
                     WHEN c.tip_valoare='suma_fixa' THEN c.valoare ELSE 0 END
            FROM base_alcf b JOIN conditii_comerciale c
                ON c.an = b.an AND c.cod_client IS NULL AND c.furnizor IS NULL
        ),
        cond_monthly AS (
            SELECT an, luna, ROUND(SUM(cost), 0) AS cost_conditii
            FROM cond_matched GROUP BY an, luna
        )
        SELECT b.an, b.luna, b.val_neta, b.marja_bruta,
            ROUND(b.marja_bruta - COALESCE(cm.cost_conditii, 0), 0) AS marja_neta
        FROM base b
        LEFT JOIN cond_monthly cm ON cm.an = b.an AND cm.luna = b.luna
        ORDER BY b.an, b.luna
    """, params)



def profitabilitate_agenti(an, max_luna=None, luna=None):
    """All agents ranked by net margin. PY filtered to same period (YTD)."""
    def _agent_rows(year, mlim=None):
        params = {'an': year}
        luna_filter = ''
        luna_filter_t = ''
        if luna is not None:
            luna_filter = 'AND luna = :luna'
            luna_filter_t = 'AND t.luna = :luna'
            params['luna'] = luna
        elif mlim is not None:
            luna_filter = 'AND luna <= :max_luna'
            luna_filter_t = 'AND t.luna <= :max_luna'
            params['max_luna'] = mlim
        return query(f"""
            WITH
            base_acf AS (
                SELECT agent, cod_client, furnizor, SUM(val_neta) AS val_neta
                FROM tranzactii WHERE an = :an {luna_filter}
                GROUP BY agent, cod_client, furnizor
            ),
            cond_by_agent AS (
                SELECT b.agent,
                    ROUND(SUM(b.val_neta * COALESCE(cr.eff_pct, 0) / 100.0
                            + COALESCE(cr.eff_fixed, 0)), 2) AS cost_conditii
                FROM base_acf b
                LEFT JOIN cond_resolved cr
                    ON cr.an = :an
                   AND cr.cod_client = b.cod_client
                   AND cr.furnizor   = b.furnizor
                GROUP BY b.agent
            )
            SELECT t.agent,
                ROUND(SUM(t.val_neta), 0)    AS val_neta,
                ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
                ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
                ROUND(SUM(t.marja_bruta) - COALESCE(ca.cost_conditii, 0), 0)       AS marja_neta,
                ROUND((SUM(t.marja_bruta) - COALESCE(ca.cost_conditii, 0))
                       * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct,
                COUNT(DISTINCT t.client)     AS nr_clienti,
                COUNT(DISTINCT t.cod_produs) AS nr_sku
            FROM tranzactii t
            LEFT JOIN cond_by_agent ca ON ca.agent = t.agent
            WHERE t.an = :an {luna_filter_t}
            GROUP BY t.agent
            ORDER BY marja_neta DESC
        """, params)

    rows_cy = _agent_rows(an, max_luna)
    py_map = {r['agent']: r for r in _agent_rows(an - 1, max_luna)}

    for row in rows_cy:
        py = py_map.get(row['agent'], {})
        row['val_neta_py'] = py.get('val_neta') or 0
        row['marja_neta_py'] = py.get('marja_neta') or 0
        row['marja_neta_pct_py'] = py.get('marja_neta_pct') or 0
        cy_mn = row.get('marja_neta') or 0
        py_mn = py.get('marja_neta') or 0
        row['delta_mn'] = round(cy_mn - py_mn, 0)
        row['delta_mn_pct'] = round((cy_mn / py_mn - 1) * 100, 1) if py_mn else None
        cy_vn = row.get('val_neta') or 0
        py_vn = py.get('val_neta') or 0
        row['delta_vn_pct'] = round((cy_vn / py_vn - 1) * 100, 1) if py_vn else None
    return rows_cy


def profitabilitate_clienti(an, limit=50, max_luna=None, luna=None):
    """Clients ranked by net margin (RON), with PY YTD comparison."""
    def _client_rows(year, mlim=None):
        params = {'an': year, 'limit': limit}
        luna_filter = ''
        luna_filter_t = ''
        if luna is not None:
            luna_filter = 'AND luna = :luna'
            luna_filter_t = 'AND t.luna = :luna'
            params['luna'] = luna
        elif mlim is not None:
            luna_filter = 'AND luna <= :max_luna'
            luna_filter_t = 'AND t.luna <= :max_luna'
            params['max_luna'] = mlim
        return query(f"""
            WITH
            base_cf AS (
                SELECT cod_client, furnizor, SUM(val_neta) AS val_neta
                FROM tranzactii WHERE an = :an {luna_filter}
                GROUP BY cod_client, furnizor
            ),
            cond_cost AS (
                SELECT b.cod_client,
                    ROUND(SUM(b.val_neta * COALESCE(cr.eff_pct, 0) / 100.0
                            + COALESCE(cr.eff_fixed, 0)), 2) AS cost_conditii
                FROM base_cf b
                LEFT JOIN cond_resolved cr
                    ON cr.an = :an
                   AND cr.cod_client = b.cod_client
                   AND cr.furnizor   = b.furnizor
                GROUP BY b.cod_client
            )
            SELECT t.client, t.cod_client, MAX(t.agent) AS agent,
                ROUND(SUM(t.val_neta), 0)    AS val_neta,
                ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
                ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
                ROUND(SUM(t.marja_bruta) - COALESCE(cc.cost_conditii, 0), 0)  AS marja_neta,
                ROUND((SUM(t.marja_bruta) - COALESCE(cc.cost_conditii, 0))
                       * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct
            FROM tranzactii t
            LEFT JOIN cond_cost cc ON cc.cod_client = t.cod_client
            WHERE t.an = :an {luna_filter_t}
            GROUP BY t.client
            ORDER BY marja_neta DESC
            LIMIT :limit
        """, params)

    rows_cy = _client_rows(an, max_luna)
    py_map = {r['cod_client']: r for r in _client_rows(an - 1, max_luna)}
    for row in rows_cy:
        py = py_map.get(row['cod_client'], {})
        row['val_neta_py']    = py.get('val_neta') or 0
        row['marja_neta_py']  = py.get('marja_neta') or 0
        cy_mn = row.get('marja_neta') or 0
        py_mn = py.get('marja_neta') or 0
        cy_vn = row.get('val_neta') or 0
        py_vn = py.get('val_neta') or 0
        row['delta_mn']     = round(cy_mn - py_mn, 0)
        row['delta_mn_pct'] = round((cy_mn / py_mn - 1) * 100, 1) if py_mn else None
        row['delta_vn_pct'] = round((cy_vn / py_vn - 1) * 100, 1) if py_vn else None
    return rows_cy


def profitabilitate_produse(an, limit=50, max_luna=None, luna=None):
    """Products ranked by net margin (RON), with PY YTD comparison.
    Uses cond_resolved for cost; SKU-level cost is proportional to vn_sku/vn_brand."""
    def _produse_rows(year, mlim=None):
        params = {'an': year, 'limit': limit}
        luna_filter = ''
        luna_filter_t = ''
        if luna is not None:
            luna_filter = 'AND luna = :luna'
            luna_filter_t = 'AND t.luna = :luna'
            params['luna'] = luna
        elif mlim is not None:
            luna_filter = 'AND luna <= :max_luna'
            luna_filter_t = 'AND t.luna <= :max_luna'
            params['max_luna'] = mlim
        return query(f"""
            WITH
            sku_vn AS (
                SELECT cod_client, furnizor, sku, SUM(val_neta) AS vn_sku
                FROM tranzactii WHERE an = :an {luna_filter}
                GROUP BY cod_client, furnizor, sku
            ),
            brand_vn AS (
                SELECT cod_client, furnizor, SUM(vn_sku) AS vn_brand
                FROM sku_vn GROUP BY cod_client, furnizor
            ),
            cond_cb AS (
                SELECT b.cod_client, b.furnizor,
                    ROUND(b.vn_brand * COALESCE(cr.eff_pct, 0) / 100.0
                        + COALESCE(cr.eff_fixed, 0), 4) AS cost_conditii
                FROM brand_vn b
                LEFT JOIN cond_resolved cr
                    ON cr.an = :an
                   AND cr.cod_client = b.cod_client
                   AND cr.furnizor   = b.furnizor
            ),
            cond_sku AS (
                SELECT s.sku, s.furnizor,
                    ROUND(SUM(ccb.cost_conditii * s.vn_sku / NULLIF(b.vn_brand, 0)), 0) AS cost_conditii
                FROM sku_vn s
                JOIN brand_vn b ON b.cod_client = s.cod_client AND b.furnizor = s.furnizor
                JOIN cond_cb ccb ON ccb.cod_client = s.cod_client AND ccb.furnizor = s.furnizor
                GROUP BY s.sku, s.furnizor
            )
            SELECT t.sku, t.furnizor,
                ROUND(SUM(t.val_neta), 0)    AS val_neta,
                ROUND(SUM(t.cantitate), 0)   AS cantitate,
                ROUND(SUM(t.marja_bruta), 0) AS marja_bruta,
                ROUND(SUM(t.marja_bruta) * 100.0 / NULLIF(SUM(t.val_neta), 0), 1) AS marja_bruta_pct,
                ROUND(SUM(t.marja_bruta) - COALESCE(cs.cost_conditii, 0), 0)       AS marja_neta,
                ROUND((SUM(t.marja_bruta) - COALESCE(cs.cost_conditii, 0))
                       * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct,
                COUNT(DISTINCT t.client) AS nr_clienti
            FROM tranzactii t
            LEFT JOIN cond_sku cs ON cs.sku = t.sku AND cs.furnizor = t.furnizor
            WHERE t.an = :an {luna_filter_t}
            GROUP BY t.sku, t.furnizor
            ORDER BY marja_neta DESC
            LIMIT :limit
        """, params)

    rows_cy = _produse_rows(an, max_luna)
    py_map = {(r['sku'], r['furnizor']): r for r in _produse_rows(an - 1, max_luna)}
    for row in rows_cy:
        py = py_map.get((row['sku'], row['furnizor']), {})
        row['val_neta_py']    = py.get('val_neta') or 0
        row['marja_neta_py']  = py.get('marja_neta') or 0
        cy_mn = row.get('marja_neta') or 0
        py_mn = py.get('marja_neta') or 0
        cy_vn = row.get('val_neta') or 0
        py_vn = py.get('val_neta') or 0
        row['delta_mn']     = round(cy_mn - py_mn, 0)
        row['delta_mn_pct'] = round((cy_mn / py_mn - 1) * 100, 1) if py_mn else None
        row['delta_vn_pct'] = round((cy_vn / py_vn - 1) * 100, 1) if py_vn else None
    return rows_cy


def profitabilitate_matrice(an, max_luna=None, luna=None):
    """Agent × Brand matrix with net margin % for heatmap (CY YTD)."""
    params = {'an': an}
    luna_filter = ''
    luna_filter_t = ''
    if luna is not None:
        luna_filter = 'AND luna = :luna'
        luna_filter_t = 'AND t.luna = :luna'
        params['luna'] = luna
    elif max_luna is not None:
        luna_filter = 'AND luna <= :max_luna'
        luna_filter_t = 'AND t.luna <= :max_luna'
        params['max_luna'] = max_luna
    return query(f"""
        WITH
        base_afc AS (
            SELECT agent, furnizor, cod_client, SUM(val_neta) AS val_neta
            FROM tranzactii WHERE an = :an {luna_filter}
            GROUP BY agent, furnizor, cod_client
        ),
        cond_by_ab AS (
            SELECT b.agent, b.furnizor,
                ROUND(SUM(b.val_neta * COALESCE(cr.eff_pct, 0) / 100.0
                        + COALESCE(cr.eff_fixed, 0)), 2) AS cost_conditii
            FROM base_afc b
            LEFT JOIN cond_resolved cr
                ON cr.an = :an
               AND cr.cod_client = b.cod_client
               AND cr.furnizor   = b.furnizor
            GROUP BY b.agent, b.furnizor
        )
        SELECT t.agent, t.furnizor,
            ROUND(SUM(t.val_neta), 0)    AS val_neta,
            ROUND(SUM(t.marja_bruta) - COALESCE(cab.cost_conditii, 0), 0)       AS marja_neta,
            ROUND((SUM(t.marja_bruta) - COALESCE(cab.cost_conditii, 0))
                   * 100.0 / NULLIF(SUM(t.val_neta), 0), 1)                    AS marja_neta_pct
        FROM tranzactii t
        LEFT JOIN cond_by_ab cab ON cab.agent = t.agent AND cab.furnizor = t.furnizor
        WHERE t.an = :an {luna_filter_t}
        GROUP BY t.agent, t.furnizor
        ORDER BY t.agent, t.furnizor
    """, params)


# ── Forecast stoc — enhanced with brand filter ───────────────────────────────

