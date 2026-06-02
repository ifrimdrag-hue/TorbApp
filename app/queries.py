import datetime
from functools import lru_cache
from db import query, query_one, get_db


def current_year():
    return datetime.date.today().year


def prior_year():
    return datetime.date.today().year - 1


def display_years():
    """Return tuple of last 3 years for trend charts (y-2, y-1, y)."""
    y = datetime.date.today().year
    return (y - 2, y - 1, y)


def _years_params(years=None):
    """Build {'y0': ..., 'y1': ..., 'y2': ...} dict for IN (:y0,:y1,:y2)."""
    yrs = years or display_years()
    return {f'y{i}': v for i, v in enumerate(yrs)}


def get_sku_cod_mare_map() -> dict:
    """Returnează {sku: cod_mare} — sursă primară stoc, fallback cod_furnizor din comenzi."""
    result = {}
    # Fallback: cod_furnizor din comenzi furnizori (acoperă SKU-uri fără stoc fizic)
    for r in query(
        "SELECT sku, MAX(cod_furnizor) AS cod_furnizor FROM comenzi_furnizori_linii "
        "WHERE cod_furnizor IS NOT NULL AND cod_furnizor != '' GROUP BY sku"
    ):
        result[r['sku']] = r['cod_furnizor']
    # Stoc are prioritate (suprascrie comenzile dacă există cod_mare)
    for r in query(
        "SELECT DISTINCT sku, cod_mare FROM stoc "
        "WHERE cod_mare IS NOT NULL AND cod_mare != ''"
    ):
        result[r['sku']] = r['cod_mare']
    return result


# ── Materialized condition costs ────────────────────────────────────────────
# `cond_resolved` precomputes, for each (an, cod_client, furnizor) combination
# that appears in tranzactii, the *aggregated* applicable conditions:
#   eff_pct   = SUM(c.valoare) for tip='pct'      matching this combo
#   eff_fixed = SUM(c.valoare) for tip='suma_fixa' matching this combo
#
# A condition matches if c.an = combo.an AND
#   (c.cod_client = combo.cod_client OR c.cod_client IS NULL) AND
#   (c.furnizor   = combo.furnizor   OR c.furnizor   IS NULL)
#
# Cost for any sale aggregate (val_neta) of (an, cod_client, furnizor) =
#   val_neta * eff_pct / 100  +  eff_fixed
#
# This eliminates the 4-way UNION ALL cond_matched CTE used in many queries
# and replaces it with a simple indexed JOIN.

_COND_RESOLVED_DDL = """
CREATE TABLE IF NOT EXISTS cond_resolved (
    an          INTEGER NOT NULL,
    cod_client  TEXT    NOT NULL,
    furnizor    TEXT    NOT NULL,
    eff_pct     REAL    NOT NULL DEFAULT 0,
    eff_fixed   REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (an, cod_client, furnizor)
)
"""

_COND_RESOLVED_REBUILD = """
INSERT INTO cond_resolved (an, cod_client, furnizor, eff_pct, eff_fixed)
SELECT
    t.an, t.cod_client, t.furnizor,
    COALESCE(SUM(CASE WHEN c.tip_valoare='pct'       THEN c.valoare END), 0),
    COALESCE(SUM(CASE WHEN c.tip_valoare='suma_fixa' THEN c.valoare END), 0)
FROM (
    SELECT DISTINCT an, cod_client, furnizor
    FROM tranzactii
    WHERE cod_client IS NOT NULL AND furnizor IS NOT NULL
) t
LEFT JOIN conditii_comerciale c
    ON c.an = t.an
   AND (c.cod_client = t.cod_client OR c.cod_client IS NULL)
   AND (c.furnizor   = t.furnizor   OR c.furnizor   IS NULL)
GROUP BY t.an, t.cod_client, t.furnizor
"""


def rebuild_cond_resolved(conn=None):
    """Repopulează tabelul materializat din scratch. Apelat după modificări de
    condiții și o dată la pornire (lazy)."""
    own = conn is None
    if own:
        conn = get_db()
    try:
        conn.execute(_COND_RESOLVED_DDL)
        conn.execute("DELETE FROM cond_resolved")
        conn.execute(_COND_RESOLVED_REBUILD)
        conn.commit()
    finally:
        if own:
            conn.close()


def ensure_cond_resolved():
    """Creează și populează tabelul dacă lipsește (apelat la pornire)."""
    conn = get_db()
    try:
        conn.execute(_COND_RESOLVED_DDL)
        n = conn.execute("SELECT COUNT(*) FROM cond_resolved").fetchone()[0]
        if n == 0:
            conn.execute(_COND_RESOLVED_REBUILD)
            conn.commit()
    finally:
        conn.close()


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


@lru_cache(maxsize=8)
def max_luna_for_year(an):
    r = query_one("SELECT MAX(luna) AS ml FROM tranzactii WHERE an = :an", {'an': an})
    return (r or {}).get('ml') or 12


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


@lru_cache(maxsize=1)
def _agents_list_cached():
    return tuple(tuple(r.items()) for r in query("""
        SELECT DISTINCT agent FROM tranzactii
        WHERE agent NOT IN ('EMAG','SITE','TRENDYOL','ALTEX')
        ORDER BY agent
    """))


def agents_list():
    return [dict(r) for r in _agents_list_cached()]


@lru_cache(maxsize=1)
def _brands_list_cached():
    return tuple(tuple(r.items()) for r in query(
        "SELECT DISTINCT furnizor FROM tranzactii ORDER BY furnizor"
    ))


def brands_list():
    return [dict(r) for r in _brands_list_cached()]


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


def bonus_team():
    return query("""
        SELECT employee_id, nume, rol, activ,
            bonus_target_lunar_ron, bonus_target_trim_ron, observatii
        FROM echipa WHERE activ = 1
        ORDER BY bonus_target_lunar_ron DESC
    """)


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


# ── Prețuri / Landing cost ───────────────────────────────────────────────────

def preturi_catalog(an=None, furnizor=None, search=None, fara_pret=False, sub_marja=None):
    if an is None:
        an = current_year()
    """Full pricing view: landing cost + selling price + margins."""
    filters, params = ["1=1"], {"an": an}
    if furnizor:
        filters.append("p.furnizor = :furnizor")
        params['furnizor'] = furnizor
    if search:
        filters.append("(p.sku LIKE :s OR p.descriere LIKE :s OR CAST(cp.cod AS TEXT) LIKE :s)")
        params['s'] = f'%{search}%'
    if fara_pret:
        filters.append("pv.pret_vanzare_ron IS NULL")
    where = " AND ".join(filters)
    rows = query(f"""
        SELECT p.sku, cp.cod AS cod_produs, p.descriere, p.furnizor, p.brand, p.categorie,
               p.gramaj, p.buc_cutie, p.ean, p.tva_pct, p.hs_code,
               p.taxa_vamala_mfn_pct, p.taxa_vamala_pct,
               p.origine, p.tara_origine,
               cl.moneda, cl.pret_achizitie_valuta, cl.curs_ron,
               cl.pret_achizitie_ron, cl.transport_pct,
               cl.taxa_vamala_pct AS lc_taxa_vamala_pct,
               cl.alte_costuri_ron, cl.landing_cost_ron,
               pv.pret_vanzare_ron,
               ROUND(pv.pret_vanzare_ron - cl.landing_cost_ron, 4) AS marja_bruta_ron,
               ROUND((pv.pret_vanzare_ron - cl.landing_cost_ron)
                     / NULLIF(pv.pret_vanzare_ron, 0) * 100, 2) AS marja_bruta_pct,
               rs.curs_ron AS curs_default
        FROM produse p
        LEFT JOIN v_sku_cod cp ON cp.sku = p.sku
        LEFT JOIN costuri_landing cl ON cl.sku = p.sku AND cl.an = :an
        LEFT JOIN preturi_vanzare pv ON pv.sku = p.sku
                  AND pv.an = :an AND pv.cod_client IS NULL AND pv.activ = 1
        LEFT JOIN rate_schimb rs ON rs.an = :an AND rs.moneda = cl.moneda
        WHERE {where} AND p.activ = 1
        ORDER BY p.furnizor, p.sku
    """, params)
    if sub_marja is not None:
        rows = [r for r in rows
                if r['marja_bruta_pct'] is not None and r['marja_bruta_pct'] < sub_marja]
    return rows


def preturi_sku(sku, an=None):
    if an is None:
        an = current_year()
    rows = query("""
        SELECT p.*, cl.*, pv.pret_vanzare_ron,
               rs.curs_ron AS curs_default,
               (SELECT cod FROM v_sku_cod WHERE v_sku_cod.sku = p.sku) AS cod_produs
        FROM produse p
        LEFT JOIN costuri_landing cl ON cl.sku = p.sku AND cl.an = :an
        LEFT JOIN preturi_vanzare pv ON pv.sku = p.sku
                  AND pv.an = :an AND pv.cod_client IS NULL
        LEFT JOIN rate_schimb rs ON rs.an = :an AND rs.moneda = cl.moneda
        WHERE p.sku = :sku
    """, {"sku": sku, "an": an})
    return rows[0] if rows else None


def preturi_client_sku(sku, an=None):
    """All client-specific prices for a SKU."""
    if an is None:
        an = current_year()
    return query("""
        SELECT pv.*, t.client
        FROM preturi_vanzare pv
        LEFT JOIN (SELECT DISTINCT cod_client, client FROM tranzactii) t
            ON t.cod_client = pv.cod_client
        WHERE pv.sku = :sku AND pv.an = :an
        ORDER BY pv.cod_client NULLS FIRST
    """, {"sku": sku, "an": an})


def preturi_update_landing(sku, an, pret_valuta, moneda, curs, transport_pct,
                           taxa_vamala_pct, alte_costuri):
    db = get_db()
    pret_ron = pret_valuta * curs
    taxa_ron = pret_ron * taxa_vamala_pct / 100
    landing  = round(pret_ron * (1 + transport_pct / 100) + taxa_ron + alte_costuri, 4)
    db.execute("""
        INSERT OR REPLACE INTO costuri_landing
            (an, sku, moneda, pret_achizitie_valuta, curs_ron, pret_achizitie_ron,
             transport_pct, taxa_vamala_pct, alte_costuri_ron, landing_cost_ron)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (an, sku, moneda, pret_valuta, curs, round(pret_ron, 4),
          transport_pct, taxa_vamala_pct, alte_costuri, landing))
    db.commit()
    db.close()
    return landing


def preturi_update_vanzare(sku, an, pret, cod_client=None):
    db = get_db()
    db.execute("""
        INSERT OR REPLACE INTO preturi_vanzare
            (an, sku, cod_client, pret_vanzare_ron, activ)
        VALUES (?,?,?,?,1)
    """, (an, sku, cod_client, pret))
    db.commit()
    db.close()


def preturi_update_produs(sku, hs_code, taxa_mfn, taxa_aplicata, tva_pct):
    db = get_db()
    db.execute("""
        UPDATE produse SET hs_code=?, taxa_vamala_mfn_pct=?, taxa_vamala_pct=?, tva_pct=?
        WHERE sku=?
    """, (hs_code, taxa_mfn, taxa_aplicata, tva_pct, sku))
    db.commit()
    db.close()


def rate_schimb_list(an=None):
    if an is None:
        an = current_year()
    return query("SELECT * FROM rate_schimb WHERE an=:an ORDER BY moneda", {"an": an})


def rate_schimb_update(an, moneda, curs):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO rate_schimb (an, moneda, curs_ron) VALUES (?,?,?)",
               (an, moneda, curs))
    db.commit()
    db.close()


def furnizori_list():
    return query("SELECT DISTINCT furnizor FROM produse WHERE activ=1 ORDER BY furnizor")


# ── Condiții comerciale ──────────────────────────────────────────────────────

def conditii_list(an=None, cod_client=None, furnizor=None):
    filters, params = [], {}
    if an:
        filters.append("c.an = :an")
        params['an'] = an
    if cod_client:
        filters.append("c.cod_client = :cod_client")
        params['cod_client'] = cod_client
    if furnizor:
        filters.append("c.furnizor = :furnizor")
        params['furnizor'] = furnizor
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    return query(f"""
        SELECT c.id, c.an, c.cod_client,
               t.client,
               c.furnizor, c.tip_valoare, c.periodicitate,
               c.valoare, c.descriere, c.data_creare
        FROM conditii_comerciale c
        LEFT JOIN (
            SELECT DISTINCT cod_client, client FROM tranzactii
        ) t ON t.cod_client = c.cod_client
        {where}
        ORDER BY c.an DESC, t.client, c.furnizor
    """, params)


def conditii_get(id):
    rows = query("SELECT * FROM conditii_comerciale WHERE id = :id", {"id": id})
    return rows[0] if rows else None


def conditii_create(an, cod_client, furnizor, tip_valoare, periodicitate, valoare, descriere):
    import datetime
    db = get_db()
    db.execute("""
        INSERT INTO conditii_comerciale
            (an, cod_client, furnizor, tip_valoare, periodicitate, valoare, descriere, data_creare)
        VALUES (?,?,?,?,?,?,?,?)
    """, (an, cod_client or None, furnizor or None, tip_valoare, periodicitate,
          valoare, descriere or None, datetime.date.today().isoformat()))
    db.commit()


def conditii_update(id, an, cod_client, furnizor, tip_valoare, periodicitate, valoare, descriere):
    db = get_db()
    db.execute("""
        UPDATE conditii_comerciale
        SET an=?, cod_client=?, furnizor=?, tip_valoare=?, periodicitate=?, valoare=?, descriere=?
        WHERE id=?
    """, (an, cod_client or None, furnizor or None, tip_valoare, periodicitate,
          valoare, descriere or None, id))
    db.commit()


def conditii_delete(id):
    db = get_db()
    db.execute("DELETE FROM conditii_comerciale WHERE id=?", (id,))
    db.commit()


def termene_list(an=None, cod_client=None):
    filters, params = [], {}
    if an:
        filters.append("t.an = :an")
        params['an'] = an
    if cod_client:
        filters.append("t.cod_client = :cod_client")
        params['cod_client'] = cod_client
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    return query(f"""
        SELECT t.id, t.an, t.cod_client, tr.client, t.zile_termen, t.observatii, t.data_creare
        FROM termene_plata t
        LEFT JOIN (SELECT DISTINCT cod_client, client FROM tranzactii) tr
            ON tr.cod_client = t.cod_client
        {where}
        ORDER BY t.an DESC, tr.client
    """, params)


def termene_create(an, cod_client, zile_termen, observatii):
    import datetime
    db = get_db()
    db.execute("""
        INSERT INTO termene_plata (an, cod_client, zile_termen, observatii, data_creare)
        VALUES (?,?,?,?,?)
    """, (an, cod_client, zile_termen, observatii or None, datetime.date.today().isoformat()))
    db.commit()


def termene_delete(id):
    db = get_db()
    db.execute("DELETE FROM termene_plata WHERE id=?", (id,))
    db.commit()


def marja_ajustata(an):
    """Adjusted margin per client/brand after applying commercial conditions."""
    return query("""
    WITH
    -- Base: annual sales + margin per client + brand
    base AS (
        SELECT cod_client, client, furnizor,
               ROUND(SUM(val_neta),2)    AS val_neta,
               ROUND(SUM(marja_bruta),2) AS marja_bruta
        FROM tranzactii WHERE an = :an
        GROUP BY cod_client, client, furnizor
    ),
    -- All applicable conditions for each client+brand (priority: specific > general)
    cond AS (
        SELECT
            b.cod_client, b.furnizor,
            -- Pick most specific condition: client+brand > client+all > all+brand > all+all
            MAX(CASE WHEN c.cod_client IS NOT NULL AND c.furnizor IS NOT NULL THEN 4
                     WHEN c.cod_client IS NOT NULL AND c.furnizor IS NULL     THEN 3
                     WHEN c.cod_client IS NULL     AND c.furnizor IS NOT NULL THEN 2
                     ELSE 1 END) AS priority,
            SUM(CASE
                WHEN c.tip_valoare='pct' AND c.periodicitate='lunar'
                    THEN b.val_neta * c.valoare / 100
                WHEN c.tip_valoare='pct' AND c.periodicitate='anual'
                    THEN b.val_neta * c.valoare / 100
                WHEN c.tip_valoare='suma_fixa'
                    THEN c.valoare
                ELSE 0 END) AS cost_conditii
        FROM base b
        JOIN conditii_comerciale c ON c.an = :an
            AND (c.cod_client = b.cod_client OR c.cod_client IS NULL)
            AND (c.furnizor   = b.furnizor   OR c.furnizor   IS NULL)
        GROUP BY b.cod_client, b.furnizor
    )
    SELECT b.cod_client, b.client, b.furnizor,
           b.val_neta, b.marja_bruta,
           ROUND(COALESCE(c.cost_conditii, 0), 2)                   AS cost_conditii,
           ROUND(b.marja_bruta - COALESCE(c.cost_conditii, 0), 2)   AS marja_ajustata,
           ROUND((b.marja_bruta - COALESCE(c.cost_conditii,0))
                 / NULLIF(b.val_neta,0) * 100, 2)                   AS marja_ajustata_pct
    FROM base b
    LEFT JOIN cond c ON c.cod_client = b.cod_client AND c.furnizor = b.furnizor
    ORDER BY b.client, b.furnizor
    """, {"an": an})


# ── Forecast stoc ────────────────────────────────────────────────────────────

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
            COUNT(DISTINCT s.sku)                                       AS nr_sku,
            ROUND(SUM(s.cantitate * s.pret_achizitie), 0)               AS valoare_totala,
            SUM(CASE WHEN zile.zile_stoc IS NOT NULL AND zile.zile_stoc < 30  THEN 1 ELSE 0 END) AS critic,
            SUM(CASE WHEN zile.zile_stoc IS NOT NULL AND zile.zile_stoc BETWEEN 30 AND 59 THEN 1 ELSE 0 END) AS atentie,
            SUM(CASE WHEN zile.zile_stoc IS NULL OR zile.zile_stoc >= 60 THEN 1 ELSE 0 END) AS ok
        FROM stoc s
        LEFT JOIN (
            SELECT s2.sku,
                CASE
                    WHEN COALESCE(v.vanzari_luna_avg, 0) > 0
                    THEN CAST(ROUND(SUM(s2.cantitate) / (v.vanzari_luna_avg / 30.0)) AS INTEGER)
                    ELSE NULL
                END AS zile_stoc
            FROM stoc s2
            LEFT JOIN (
                SELECT sku, SUM(cantitate) / 3.0 AS vanzari_luna_avg
                FROM tranzactii
                WHERE data_dl >= date('now', '-90 days')
                GROUP BY sku
            ) v ON s2.sku = v.sku
            WHERE s2.data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
              AND s2.cantitate > 0
            GROUP BY s2.sku
        ) zile ON s.sku = zile.sku
        WHERE s.data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
          AND s.cantitate > 0
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
               COALESCE(ROUND(v_split.avg_hu, 1), 0)          AS avg_monthly_hu
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
        WHERE s.data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
          AND s.cantitate > 0 {where}
        GROUP BY s.sku, s.furnizor, s.gama
        ORDER BY zile_stoc ASC NULLS LAST, valoare_stoc DESC
    """, params)

    import forecast_logic

    transit_by_sku = {}
    transit_sku_meta = {}  # {sku: {'furnizor': ..., 'cod_produs': ...}}
    for r in query("""
        SELECT l.sku, c.nr_comanda, c.furnizor, c.data_estimata_livrare AS eta,
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
            r['zile_stoc'] = int(available / (avg_total / 30))

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
        zile_stoc = int(available / (avg_total / 30)) if avg_total > 0 else None

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

def termene_aprovizionare_list():
    return query("SELECT * FROM termene_aprovizionare ORDER BY furnizor")


def termene_partial_update(furnizor: str, zile: int, sezon_craciun: int = 0, observatii: str = None):
    """Actualizează doar zile_livrare, sezon_craciun, observatii — tab Termene din forecast."""
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO termene_aprovizionare (furnizor, zile_livrare, sezon_craciun, observatii)
            VALUES (:f, :z, :s, :o)
            ON CONFLICT(furnizor) DO UPDATE SET
                zile_livrare  = excluded.zile_livrare,
                sezon_craciun = excluded.sezon_craciun,
                observatii    = excluded.observatii
        """, {'f': furnizor, 'z': zile, 's': sezon_craciun, 'o': observatii})
        conn.commit()
    finally:
        conn.close()


# ── Comenzi furnizori ─────────────────────────────────────────────────────────

def comenzi_list(furnizor=None, status=None):
    filters, params = [], {}
    if furnizor:
        filters.append("c.furnizor = :furnizor")
        params['furnizor'] = furnizor
    if status:
        filters.append("c.status = :status")
        params['status'] = status
    where = ('WHERE ' + ' AND '.join(filters)) if filters else ''
    return query(f"""
        SELECT c.id, c.nr_comanda, c.furnizor, c.data_comanda, c.status,
               c.data_estimata_livrare, c.data_confirmare_furnizor, c.observatii,
               c.created_at, c.updated_at,
               COUNT(l.id)  AS nr_linii,
               SUM(COALESCE(l.cantitate_confirmata, l.cantitate_comandata)) AS total_qty,
               SUM(COALESCE(l.cantitate_ro, 0))     AS total_ro,
               SUM(COALESCE(l.cantitate_export, 0)) AS total_export
        FROM comenzi_furnizori c
        LEFT JOIN comenzi_furnizori_linii l ON l.comanda_id = c.id
        {where}
        GROUP BY c.id
        ORDER BY c.data_comanda DESC, c.id DESC
    """, params)


def comanda_get(comanda_id: int) -> dict | None:
    h = query_one("SELECT * FROM comenzi_furnizori WHERE id = :id", {'id': comanda_id})
    if not h:
        return None
    lines = query("""
        SELECT l.id, l.sku, l.cantitate_sugerat, l.cantitate_comandata,
               l.cantitate_ro, l.cantitate_export,
               l.cantitate_confirmata, l.pret_valuta, l.moneda, l.observatii,
               l.cod_furnizor, l.units_per_carton, l.cantitate_baxuri,
               l.gross_kg, l.net_kg, l.cbm, l.total_valuta,
               COALESCE(l.descriere, p.descriere, l.sku) AS descriere,
               COALESCE(l.cod_furnizor, (SELECT cod FROM v_sku_cod WHERE v_sku_cod.sku = l.sku)) AS cod_produs
        FROM comenzi_furnizori_linii l
        LEFT JOIN produse p ON p.sku = l.sku
        WHERE l.comanda_id = :id ORDER BY l.sku
    """, {'id': comanda_id})
    return {'header': dict(h), 'lines': lines}


def comanda_create(furnizor: str, nr_comanda: str = None, observatii: str = None) -> int:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO comenzi_furnizori (furnizor, nr_comanda, observatii) VALUES (:f, :nr, :obs)",
            {'f': furnizor, 'nr': nr_comanda, 'obs': observatii}
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def comanda_update(comanda_id: int, **kwargs):
    allowed = {'nr_comanda', 'status', 'data_estimata_livrare',
               'data_confirmare_furnizor', 'observatii'}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return
    sets = ', '.join(f"{k} = :{k}" for k in fields)
    fields['id'] = comanda_id
    import datetime as _dt
    fields['now'] = _dt.datetime.now().isoformat()
    conn = get_db()
    try:
        conn.execute(
            f"UPDATE comenzi_furnizori SET {sets}, updated_at = :now WHERE id = :id",
            fields
        )
        conn.commit()
    finally:
        conn.close()


def comanda_delete(comanda_id: int):
    conn = get_db()
    try:
        conn.execute("DELETE FROM comenzi_furnizori WHERE id = :id", {'id': comanda_id})
        conn.commit()
    finally:
        conn.close()


def comanda_line_upsert(comanda_id: int, sku: str, cantitate_comandata: int,
                         cantitate_sugerat: int = 0, pret_valuta: float = None,
                         moneda: str = 'EUR', observatii: str = None,
                         cantitate_ro: int = 0, cantitate_export: int = 0,
                         cod_furnizor: str = None) -> int:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM comenzi_furnizori_linii WHERE comanda_id=:cid AND sku=:sku",
            {'cid': comanda_id, 'sku': sku}
        ).fetchone()
        if row:
            conn.execute("""
                UPDATE comenzi_furnizori_linii
                SET cantitate_comandata=:qty, cantitate_sugerat=:sq,
                    cantitate_ro=:qro, cantitate_export=:qexp,
                    pret_valuta=:pv, moneda=:m, observatii=:obs,
                    cod_furnizor=COALESCE(:cf, cod_furnizor)
                WHERE id=:id
            """, {'qty': cantitate_comandata, 'sq': cantitate_sugerat,
                  'qro': cantitate_ro, 'qexp': cantitate_export,
                  'pv': pret_valuta, 'm': moneda, 'obs': observatii,
                  'cf': cod_furnizor, 'id': row[0]})
            lid = row[0]
        else:
            cur = conn.execute("""
                INSERT INTO comenzi_furnizori_linii
                    (comanda_id, sku, cantitate_sugerat, cantitate_comandata,
                     cantitate_ro, cantitate_export, pret_valuta, moneda, observatii, cod_furnizor)
                VALUES (:cid, :sku, :sq, :qty, :qro, :qexp, :pv, :m, :obs, :cf)
            """, {'cid': comanda_id, 'sku': sku, 'sq': cantitate_sugerat,
                  'qty': cantitate_comandata, 'qro': cantitate_ro, 'qexp': cantitate_export,
                  'pv': pret_valuta, 'm': moneda, 'obs': observatii, 'cf': cod_furnizor})
            lid = cur.lastrowid
        conn.commit()
        return lid
    finally:
        conn.close()


def comanda_line_update(line_id: int, **kwargs):
    allowed = {'cantitate_comandata', 'cantitate_confirmata', 'cantitate_ro', 'cantitate_export',
               'pret_valuta', 'moneda', 'observatii', 'cod_furnizor'}
    # Filter out None — `cantitate_comandata` has NOT NULL constraint and the
    # JS often sends only the field user actually edited.
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return
    sets = ', '.join(f"{k} = :{k}" for k in fields)
    fields['id'] = line_id
    conn = get_db()
    try:
        conn.execute(f"UPDATE comenzi_furnizori_linii SET {sets} WHERE id = :id", fields)
        conn.commit()
    finally:
        conn.close()


def comanda_line_delete(line_id: int):
    conn = get_db()
    try:
        conn.execute("DELETE FROM comenzi_furnizori_linii WHERE id = :id", {'id': line_id})
        conn.commit()
    finally:
        conn.close()


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

BASILUR_BRANDS = ('Basilur', 'KingsLeaf', 'Tipson')
_BASILUR_IN    = "('Basilur','KingsLeaf','Tipson')"


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

def get_export_hu_codes() -> set:
    """Set de cod_client care mapează la bucketul HU (gestiune separată)."""
    rows = query("""
        SELECT ce.cod_client
        FROM clienti_export ce
        JOIN tari_export te ON ce.tara_id = te.id
        WHERE ce.activ = 1 AND te.piata = 'HU'
    """)
    return {r['cod_client'] for r in rows}


def monthly_sales_ro_hu(furnizor: str | None) -> dict:
    """Vânzări medii lunare per SKU, split RO/HU strict separate.
    Returnează {sku: {'ro': {1..12: qty}, 'hu': {1..12: qty},
                      'ro_prev': {1..12: qty}, 'hu_prev': {1..12: qty},
                      'cod_produs': str}}
    """
    from datetime import date
    from db import _conn, has_app_context
    hu_codes = get_export_hu_codes()
    hu_list  = list(hu_codes) if hu_codes else ['~~EMPTY~~']

    hu_ph = ','.join(['?' for _ in hu_list])

    furn_where = "AND furnizor = ?" if furnizor else ""
    sql = f"""
        SELECT
            sku, cod_produs, luna, an,
            SUM(CASE WHEN cod_client NOT IN ({hu_ph}) THEN cantitate ELSE 0 END) AS qty_ro,
            SUM(CASE WHEN cod_client IN     ({hu_ph}) THEN cantitate ELSE 0 END) AS qty_hu
        FROM tranzactii
        WHERE an >= ?
          AND cantitate > 0
          {furn_where}
        GROUP BY sku, cod_produs, luna, an
        ORDER BY sku, an, luna
    """

    today = date.today()
    an_start = today.year - 2
    params = hu_list + hu_list + [an_start]
    if furnizor:
        params.append(furnizor)

    conn = _conn()
    transient = not has_app_context()
    try:
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        if transient:
            conn.close()

    result = {}
    for r in rows:
        sku = r['sku']
        if sku not in result:
            result[sku] = {
                'cod_produs': r['cod_produs'],
                'ro': {}, 'hu': {}, 'ro_prev': {}, 'hu_prev': {}
            }
        m = r['luna']
        if r['an'] == today.year:
            result[sku]['ro'][m] = result[sku]['ro'].get(m, 0) + r['qty_ro']
            result[sku]['hu'][m] = result[sku]['hu'].get(m, 0) + r['qty_hu']
        else:
            result[sku]['ro_prev'][m] = result[sku]['ro_prev'].get(m, 0) + r['qty_ro']
            result[sku]['hu_prev'][m] = result[sku]['hu_prev'].get(m, 0) + r['qty_hu']
    return result


def stoc_ro_hu(furnizor: str = None) -> dict:
    """Stoc fizic per SKU per piață (RO/HU) din ultimul snapshot.
    Returnează {sku: {'ro': qty, 'hu': qty, 'val_ro': val, 'val_hu': val,
                      'cod_produs': str, 'gama': str, 'furnizor': str,
                      'data_intrare_min': str}}
    """
    where = "AND furnizor = :furnizor" if furnizor else ""
    rows = query(f"""
        SELECT sku, cod_produs, gama, furnizor,
               COALESCE(piata,'RO') AS piata,
               SUM(cantitate) AS qty,
               SUM(cantitate * pret_achizitie) AS val,
               MIN(data_intrare) AS data_intrare_min
        FROM stoc
        WHERE data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
          {where}
        GROUP BY sku, cod_produs, gama, furnizor, piata
    """, {'furnizor': furnizor} if furnizor else {})

    result = {}
    for r in rows:
        sku = r['sku']
        if sku not in result:
            result[sku] = {
                'cod_produs': r['cod_produs'], 'gama': r['gama'],
                'furnizor': r['furnizor'], 'descriere': '',
                'ro': 0.0, 'hu': 0.0, 'val_ro': 0.0, 'val_hu': 0.0,
                'data_intrare_min': r['data_intrare_min'],
            }
        if r['piata'] == 'HU':
            result[sku]['hu']     += r['qty'] or 0
            result[sku]['val_hu'] += r['val'] or 0
        else:
            result[sku]['ro']     += r['qty'] or 0
            result[sku]['val_ro'] += r['val'] or 0
    return result


def in_transit_ro_hu(furnizor: str) -> dict:
    """Cantitate în tranzit per SKU per piată din comenzi active.
    Status active: 'Emisa', 'Confirmata', 'In tranzit'.
    Returnează {sku: {'ro': qty, 'hu': qty, 'comenzi': [...]}}
    """
    rows = query("""
        SELECT
            l.sku,
            cf.nr_comanda, cf.data_comanda, cf.status,
            cf.data_estimata_livrare AS eta,
            COALESCE(l.cantitate_confirmata, l.cantitate_comandata, 0) AS qty_total,
            COALESCE(l.cantitate_ro, 0)     AS qty_ro,
            COALESCE(l.cantitate_export, 0) AS qty_hu
        FROM comenzi_furnizori_linii l
        JOIN comenzi_furnizori cf ON cf.id = l.comanda_id
        WHERE cf.furnizor = :furnizor
          AND cf.status IN ('Emisa','Confirmata','In tranzit')
        ORDER BY cf.data_comanda
    """, {'furnizor': furnizor})

    result = {}
    for r in rows:
        sku = r['sku']
        if sku not in result:
            result[sku] = {'ro': 0, 'hu': 0, 'comenzi': []}
        result[sku]['ro'] += r['qty_ro']
        result[sku]['hu'] += r['qty_hu']
        result[sku]['comenzi'].append({
            'nr_comanda':   r['nr_comanda'],
            'data_comanda': r['data_comanda'],
            'eta':          r['eta'],
            'status':       r['status'],
            'qty_ro':       r['qty_ro'],
            'qty_hu':       r['qty_hu'],
        })
    return result


def expirare_list(furnizor: str = None, prag_luni: int = 6, tip_produs: str = None) -> list:
    """Articole cu data_intrare mai veche de prag_luni luni din stoc_expirare."""
    from datetime import date, timedelta
    data_limita = (date.today() - timedelta(days=prag_luni * 30)).isoformat()

    where_parts = ["data_intrare IS NOT NULL", "data_intrare <= :data_limita", "cantitate > 0"]
    params = {'data_limita': data_limita}
    if furnizor:
        where_parts.append("furnizor = :furnizor")
        params['furnizor'] = furnizor

    inner_where = " AND ".join(where_parts)

    outer_tip_filter = ""
    if tip_produs:
        outer_tip_filter = "WHERE tip_produs_calc = :tip"
        params['tip'] = tip_produs

    rows = query(f"""
        SELECT * FROM (
            SELECT
                se.sku, se.cod_produs, se.furnizor, se.gama,
                se.data_intrare, se.data_expirare, se.cantitate,
                COALESCE(se.pret_achizitie, 0) * se.cantitate AS valoare,
                CAST(julianday('now') - julianday(se.data_intrare) AS INTEGER) AS vechime_zile,
                CASE
                    WHEN se.furnizor IN ('Basilur','KingsLeaf','Tipson','Organsia','Celmar') THEN 'Ceai'
                    WHEN se.furnizor IN ('Toras','Delaviuda') THEN 'Ciocolata'
                    ELSE 'Altele'
                END AS tip_produs_calc
            FROM stoc_expirare se
            WHERE {inner_where}
        )
        {outer_tip_filter}
        ORDER BY data_intrare ASC
    """, params)
    return rows


def tari_export_list() -> list:
    return query("SELECT * FROM tari_export ORDER BY tara")


def tari_export_upsert(tara: str, piata: str, activ: int, observatii: str = None, id: int = None):
    db = get_db()
    try:
        if id is not None:
            db.execute(
                "UPDATE tari_export SET tara=?,piata=?,activ=?,observatii=? WHERE id=?",
                (tara, piata, activ, observatii, id)
            )
        else:
            db.execute(
                "INSERT INTO tari_export (tara,piata,activ,observatii) VALUES (?,?,?,?)",
                (tara, piata, activ, observatii)
            )
        db.commit()
    finally:
        db.close()


def tari_export_delete(id: int):
    db = get_db()
    try:
        db.execute("DELETE FROM clienti_export WHERE tara_id=?", (id,))
        db.execute("DELETE FROM tari_export WHERE id=?", (id,))
        db.commit()
    finally:
        db.close()


def clienti_export_list() -> list:
    return query("""
        SELECT ce.*, te.tara, te.piata
        FROM clienti_export ce
        JOIN tari_export te ON ce.tara_id = te.id
        ORDER BY te.tara, ce.nume_client
    """)


def clienti_export_upsert(tara_id: int, cod_client: str, nume_client: str,
                           activ: int, observatii: str = None, id: int = None):
    db = get_db()
    try:
        if id is not None:
            db.execute(
                "UPDATE clienti_export SET tara_id=?,cod_client=?,nume_client=?,activ=?,observatii=? WHERE id=?",
                (tara_id, cod_client, nume_client, activ, observatii, id)
            )
        else:
            db.execute(
                "INSERT INTO clienti_export (tara_id,cod_client,nume_client,activ,observatii) VALUES (?,?,?,?,?)",
                (tara_id, cod_client, nume_client, activ, observatii)
            )
        db.commit()
    finally:
        db.close()


def clienti_export_toggle(id: int):
    db = get_db()
    try:
        db.execute("UPDATE clienti_export SET activ = 1 - activ WHERE id=?", (id,))
        db.commit()
    finally:
        db.close()


def termene_aprovizionare_upsert(furnizor: str, zile_min: int, zile_max: int, moneda: str,
                                 tip_produs: str, sezon_craciun: int, observatii: str = None):
    db = get_db()
    try:
        db.execute("""
            INSERT INTO termene_aprovizionare
                (furnizor, zile_livrare_min, zile_livrare, moneda, tip_produs, sezon_craciun, observatii)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(furnizor) DO UPDATE SET
                zile_livrare_min=excluded.zile_livrare_min,
                zile_livrare=excluded.zile_livrare,
                moneda=excluded.moneda,
                tip_produs=excluded.tip_produs,
                sezon_craciun=excluded.sezon_craciun,
                observatii=excluded.observatii
        """, (furnizor, zile_min, zile_max, moneda, tip_produs, sezon_craciun, observatii))
        db.commit()
    finally:
        db.close()
