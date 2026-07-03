"""
Migration 0013 -- corr_vanzari_tobra cost table.

Torb->Tobra invoice lines (cod_client=719) are diverted here by
etl/import_vanzari_erp.py instead of being dropped. Holds Torb's true
acquisition cost per product over time; consumed by
etl/import_vanzari_tobra_auchan.py to override pret_cumparare on
imported Tobra->Auchan rows. Idempotent.
"""

VERSION = 13
NAME = "0013_20260702_vanzari_tobra"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS corr_vanzari_tobra (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            data_dl        TEXT,
            nr_dl          TEXT,
            nr_factura     TEXT,
            cod_produs     TEXT,
            sku            TEXT,
            cantitate      REAL,
            pret_cumparare REAL,
            pret_vanzare   REAL,
            UNIQUE(nr_dl, cod_produs, nr_factura, pret_vanzare)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_corr_vanzari_tobra_cod_data"
        " ON corr_vanzari_tobra(cod_produs, data_dl)"
    )
