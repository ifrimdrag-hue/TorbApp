"""
Fix v_clienti.agent_principal to always reflect the most recent transaction.

Previously, GROUP BY client with bare `agent` column let SQLite pick an
arbitrary row — typically from older data — so a client moved to a new agent
would still show the old one after import.
"""

VERSION = 3
NAME = "fix_agent_principal"


def up(conn):
    conn.execute("DROP VIEW IF EXISTS v_clienti")
    conn.execute("""
        CREATE VIEW v_clienti AS
        SELECT
            t1.client,
            t1.cod_client,
            t1.cui_client,
            t1.tip_client,
            t1.oras_client,
            t1.judet_client,
            MIN(t1.data_dl)                    AS prima_comanda,
            MAX(t1.data_dl)                    AS ultima_comanda,
            ROUND(SUM(t1.val_neta), 2)         AS val_neta_total,
            ROUND(SUM(t1.marja_bruta), 2)      AS marja_totala,
            COUNT(DISTINCT t1.nr_factura)      AS nr_facturi,
            COUNT(DISTINCT t1.furnizor)        AS nr_branduri,
            (SELECT t2.agent FROM tranzactii t2
             WHERE t2.client = t1.client
             ORDER BY t2.data_dl DESC, t2.rowid DESC
             LIMIT 1)                          AS agent_principal
        FROM tranzactii t1
        GROUP BY t1.client
    """)
