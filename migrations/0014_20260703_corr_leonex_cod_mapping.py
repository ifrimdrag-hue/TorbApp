"""
Migration 0014 -- corr_leonex_cod_mapping.

Maps Leonex supplier article codes (MK...) to Torb internal codes (cod_mare,
"Cod TORB"). Consumed by etl/import_comenzi_tranzit_leonex.py so imported order
lines resolve to the correct Torb product and merge into the stock/orders view.
Idempotent.
"""

VERSION = 14
NAME = "0014_20260703_corr_leonex_cod_mapping"

SEED = [
    ("MK001730", "1683"),
    ("MK001728", "1571"),
    ("MK000928", "584"),
    ("MK001731", "1574"),
    ("MK000497", "580"),
    ("MK000493", "579"),
    ("MK000927", "978"),
    ("MK001729", "1570"),
    ("MK000929", "583"),
    ("MK001899", "1701"),
]


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS corr_leonex_cod_mapping (
            cod_furnizor TEXT PRIMARY KEY,
            cod_torb     TEXT NOT NULL
        )
    """)
    conn.executemany(
        "INSERT OR IGNORE INTO corr_leonex_cod_mapping (cod_furnizor, cod_torb) VALUES (?, ?)",
        SEED,
    )
