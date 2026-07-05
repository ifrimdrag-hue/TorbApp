"""Migration 0023 - dedupe standard prices in preturi_vanzare.

UNIQUE(an, sku, cod_client) never fires for the standard price rows because
SQLite treats NULLs as distinct, so every re-import/save stacked another
cod_client IS NULL row (289 SKUs affected). Keep the newest row per (an, sku)
and add a partial unique index so INSERT OR REPLACE upserts correctly from
now on.
"""

VERSION = 23
NAME = "0023_20260706_preturi_vanzare_dedupe"


def up(conn):
    conn.execute("""
        DELETE FROM preturi_vanzare
        WHERE cod_client IS NULL
          AND id NOT IN (
              SELECT MAX(id) FROM preturi_vanzare
              WHERE cod_client IS NULL
              GROUP BY an, sku
          )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_pv_standard_unic
        ON preturi_vanzare(an, sku) WHERE cod_client IS NULL
    """)
