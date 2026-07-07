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


def pnl_config_rows():
    return query("SELECT * FROM pnl_config ORDER BY pnl_line")


def pnl_import_log(limit=50):
    return query(
        "SELECT * FROM pnl_import_log ORDER BY timestamp DESC LIMIT ?", (limit,))
