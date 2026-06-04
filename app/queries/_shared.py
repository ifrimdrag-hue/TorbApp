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



@lru_cache(maxsize=8)
def max_luna_for_year(an):
    r = query_one("SELECT MAX(luna) AS ml FROM tranzactii WHERE an = :an", {'an': an})
    return (r or {}).get('ml') or 12


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



def furnizori_list():
    return query("SELECT DISTINCT furnizor FROM produse WHERE activ=1 ORDER BY furnizor")


# ── Condiții comerciale ──────────────────────────────────────────────────────




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

