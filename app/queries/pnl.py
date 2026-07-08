"""Read queries for the P&L module. All reads via host db.query."""
from db import query


def pnl_available_years():
    return [r['an'] for r in query(
        "SELECT DISTINCT an FROM pnl_balante_raw ORDER BY an")]


def pnl_available_months(an, entitate):
    if entitate == 'grup':
        rows = query(
            "SELECT DISTINCT luna FROM pnl_balante_raw WHERE an=? ORDER BY luna", (an,))
    else:
        rows = query(
            "SELECT DISTINCT luna FROM pnl_balante_raw WHERE entitate=? AND an=? ORDER BY luna",
            (entitate, an))
    return [r['luna'] for r in rows]


def pnl_mapping():
    return {r['cont']: (r['pnl_line'], int(r['semn']))
            for r in query("SELECT cont, pnl_line, semn FROM pnl_mapping_conturi")}


def pnl_alarm_config():
    return {r['pnl_line']: dict(r)
            for r in query("SELECT * FROM pnl_config")}


def pnl_rulcd(entitate, an, luna):
    return {r['cont']: r['rulcd'] for r in query(
        "SELECT cont, rulcd FROM pnl_balante_raw WHERE entitate=? AND an=? AND luna=?",
        (entitate, an, luna))}


def pnl_mapping_rows():
    return query(
        "SELECT cont, dencont, pnl_line, semn, categorie "
        "FROM pnl_mapping_conturi ORDER BY pnl_line, cont")


def pnl_unmapped_accounts():
    """Class 6/7 accounts seen in imported balances but absent from the mapping."""
    return query("""
        SELECT b.cont, MAX(b.dencont) AS dencont,
               GROUP_CONCAT(DISTINCT b.entitate) AS entitati,
               MIN(b.an) AS din_an, MAX(b.an) AS pana_an
        FROM pnl_balante_raw b
        WHERE (b.cont LIKE '6%' OR b.cont LIKE '7%') AND b.rulcd != 0
          AND b.cont NOT IN (SELECT cont FROM pnl_mapping_conturi)
        GROUP BY b.cont ORDER BY b.cont
    """)


def pnl_config_rows():
    return query("SELECT * FROM pnl_config ORDER BY pnl_line")


def pnl_import_log(limit=50):
    return query(
        "SELECT * FROM pnl_import_log ORDER BY timestamp DESC LIMIT ?", (limit,))
