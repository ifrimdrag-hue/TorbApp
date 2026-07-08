"""Solduri neincasate (accounts-receivable aging) queries.

Reference date = today. Due date is derived per row as datadl + term_pl_cl.
`d` = signed whole days from today to the due date (negative = overdue).
Buckets are disjoint ranges (1-7 / 8-30 / 31-60 / >60 on each side); every
row (incl. negative advances/credit notes) falls in exactly one, so the
cards reconcile exactly to Total in piata. Terminology: "In termen" (d >= 0)
/ "Scadenta depasita" (d <= -1).
"""
from db import query, query_one

# signed whole days from today to due date (negative = overdue)
_days_expr = (
    "CAST(julianday(date(datadl, '+' || COALESCE(term_pl_cl,0) || ' days')) "
    "- julianday(date('now','localtime')) AS INTEGER)"
)

_scadenta_expr = "date(datadl, '+' || COALESCE(term_pl_cl,0) || ' days')"

BUCKET_KEYS = ("nesc7", "nesc30", "nesc60", "nesc60p",
               "scad7", "scad30", "scad60", "scad60p", "total_scadent")

# disjoint ranges; d=0 (due today) counts as still in term
_BUCKET_PRED = {
    "nesc7":         f"{_days_expr} BETWEEN 0 AND 7",
    "nesc30":        f"{_days_expr} BETWEEN 8 AND 30",
    "nesc60":        f"{_days_expr} BETWEEN 31 AND 60",
    "nesc60p":       f"{_days_expr} > 60",
    "scad7":         f"{_days_expr} BETWEEN -7 AND -1",
    "scad30":        f"{_days_expr} BETWEEN -30 AND -8",
    "scad60":        f"{_days_expr} BETWEEN -60 AND -31",
    "scad60p":       f"{_days_expr} < -60",
    "total_scadent": f"{_days_expr} <= -1",
}


def _bucket_where(bucket):
    pred = _BUCKET_PRED.get(bucket)
    return f" AND {pred}" if pred else ""


def _total_case(bucket):
    """SUM scoped to the active bucket, else the full balance."""
    bwhere = _bucket_where(bucket)
    if bwhere:
        return f"SUM(CASE WHEN 1=1{bwhere} THEN sumdeincas ELSE 0 END)"
    return "SUM(sumdeincas)"


def _bucket_sum_cols():
    return ", ".join(
        f"ROUND(SUM(CASE WHEN {_BUCKET_PRED[k]} THEN sumdeincas ELSE 0 END),2) AS {k}"
        for k in ("nesc7", "nesc30", "nesc60", "nesc60p",
                  "scad7", "scad30", "scad60", "scad60p")
    )


def _filters(agent, search):
    where, params = "", {}
    if agent:
        where += " AND numeag = :agent"
        params["agent"] = agent
    if search:
        where += " AND numecli LIKE :search"
        params["search"] = f"%{search}%"
    return where, params


# ── meta + KPI ───────────────────────────────────────────────────────────────

def solduri_meta():
    return query_one(
        "SELECT MAX(data_raport) AS data_raport, COUNT(*) AS nr_randuri "
        "FROM solduri_neincasate"
    )


def solduri_kpi(agent=None, search=None):
    """Aging cards, scoped to the active agent/client filters (default: whole market)."""
    fwhere, params = _filters(agent, search)
    keys = (*BUCKET_KEYS, "total_piata")
    sums = ", ".join(
        f"ROUND(SUM(CASE WHEN {pred} THEN sumdeincas ELSE 0 END), 2) AS {key}"
        for key, pred in _BUCKET_PRED.items()
    )
    row = query_one(
        f"SELECT {sums}, ROUND(SUM(sumdeincas),2) AS total_piata "
        f"FROM solduri_neincasate WHERE 1=1{fwhere}",
        params,
    )
    return {k: (row[k] or 0) for k in keys} if row else {k: 0 for k in keys}


# ── table views ──────────────────────────────────────────────────────────────

def solduri_agents():
    rows = query("SELECT DISTINCT numeag FROM solduri_neincasate "
                 "WHERE numeag IS NOT NULL ORDER BY numeag")
    return [r["numeag"] for r in rows]


def solduri_by_client(bucket=None, agent=None, search=None):
    fwhere, params = _filters(agent, search)
    total_case = _total_case(bucket)
    return query(f"""
        SELECT numecli, MIN(codcli) AS codcli, MIN(numeag) AS numeag,
               ROUND({total_case},2) AS total,
               {_bucket_sum_cols()},
               MAX(plafon) AS plafon,
               MAX(CASE WHEN {_days_expr} <= -1 THEN -({_days_expr}) ELSE 0 END)
                   AS zile_restanta_max,
               CASE WHEN MAX(plafon) > 0 AND ROUND(SUM(sumdeincas),2) > MAX(plafon)
                    THEN 1 ELSE 0 END AS depasit_plafon
        FROM solduri_neincasate
        WHERE 1=1{fwhere}
        GROUP BY numecli
        HAVING ROUND({total_case},2) <> 0
        ORDER BY total DESC
    """, params)


def solduri_by_agent(bucket=None, search=None):
    fwhere, params = _filters(None, search)
    total_case = _total_case(bucket)
    return query(f"""
        SELECT numeag,
               ROUND({total_case},2) AS total,
               {_bucket_sum_cols()},
               COUNT(DISTINCT codcli) AS nr_clienti
        FROM solduri_neincasate
        WHERE 1=1{fwhere}
        GROUP BY numeag
        HAVING ROUND({total_case},2) <> 0
        ORDER BY total DESC
    """, params)


_BUCKET_LABEL = (
    f"CASE "
    f"WHEN {_days_expr} BETWEEN 0 AND 7 THEN 'În termen 1-7 zile' "
    f"WHEN {_days_expr} BETWEEN 8 AND 30 THEN 'În termen 8-30 zile' "
    f"WHEN {_days_expr} BETWEEN 31 AND 60 THEN 'În termen 31-60 zile' "
    f"WHEN {_days_expr} > 60 THEN 'În termen >60 zile' "
    f"WHEN {_days_expr} BETWEEN -7 AND -1 THEN 'Depășit 1-7 zile' "
    f"WHEN {_days_expr} BETWEEN -30 AND -8 THEN 'Depășit 8-30 zile' "
    f"WHEN {_days_expr} BETWEEN -60 AND -31 THEN 'Depășit 31-60 zile' "
    f"ELSE 'Depășit >60 zile' END"
)


def solduri_by_invoice(bucket=None, agent=None, search=None, codcli=None):
    fwhere, params = _filters(agent, search)
    if codcli:
        fwhere += " AND codcli = :codcli"
        params["codcli"] = codcli
    bwhere = _bucket_where(bucket)
    return query(f"""
        SELECT factout, numecli, codcli, numeag, datadl,
               {_scadenta_expr} AS scadenta, term_pl_cl, sumdeincas,
               cec, scad_cec, cec_val,
               {_days_expr} AS zile,
               {_BUCKET_LABEL} AS bucket_label
        FROM solduri_neincasate
        WHERE 1=1{fwhere}{bwhere}
        ORDER BY scadenta ASC, factout
    """, params)


def solduri_client_header(codcli):
    """Aggregate card for one client's open balance (None-safe: check nr_documente)."""
    return query_one(f"""
        SELECT MIN(numecli) AS numecli, MIN(codcli) AS codcli,
               MIN(numeag) AS numeag, MIN(telefon) AS telefon, MIN(canal) AS canal,
               MAX(plafon) AS plafon,
               ROUND(SUM(sumdeincas),2) AS total,
               ROUND(COALESCE(SUM(cec_val),0),2) AS total_cec,
               ROUND(SUM(sumdeincas) - COALESCE(SUM(cec_val),0),2) AS total_neacoperit,
               ROUND(SUM(CASE WHEN {_days_expr} <= -1 THEN sumdeincas ELSE 0 END),2)
                   AS total_scadent,
               {_bucket_sum_cols()},
               MAX(CASE WHEN {_days_expr} <= -1 THEN -({_days_expr}) ELSE 0 END)
                   AS zile_restanta_max,
               COUNT(*) AS nr_documente,
               CASE WHEN MAX(plafon) > 0 AND ROUND(SUM(sumdeincas),2) > MAX(plafon)
                    THEN 1 ELSE 0 END AS depasit_plafon
        FROM solduri_neincasate
        WHERE codcli = :codcli
    """, {"codcli": codcli})
