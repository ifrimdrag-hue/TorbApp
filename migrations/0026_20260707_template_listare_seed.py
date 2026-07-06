"""Migration 0026 - default listing template per known client.

Maps clients to the xls layout their file must follow (F3). Assignment is
data in clienti_pricing.template_listare, resolved by client name from
tranzactii - nothing hardcoded to client codes. Only fills NULLs, so a
value changed in the UI later always wins.
"""

VERSION = 26
NAME = "0026_20260707_template_listare_seed"

_MAP = {
    '%KAUFLAND%': 'kaufland_modificare',
    '%SELGROS%': 'selgros_lista',
    '%FILDAS%': 'fildas_lista',
    '%SEZAMO%': 'sezamo_lista',
}


def up(conn):
    for pattern, template in _MAP.items():
        rows = conn.execute(
            "SELECT DISTINCT cod_client, client FROM tranzactii "
            "WHERE upper(client) LIKE upper(?)", (pattern,)).fetchall()
        if len(rows) != 1:
            continue  # unknown or ambiguous on this DB - leave for the UI
        cod, nume = rows[0]
        conn.execute(
            "INSERT INTO clienti_pricing (cod_client, nume_client, template_listare)"
            " VALUES (?, ?, ?)"
            " ON CONFLICT(cod_client) DO UPDATE SET"
            " template_listare = COALESCE(template_listare, excluded.template_listare)",
            (cod, nume, template))
