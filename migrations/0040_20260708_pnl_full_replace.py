"""Migration 0040 - P&L F0 correctness foundation schema.

Two schema changes for the F0 phase:

1. Rebuild ``pnl_balante_raw`` so the UNIQUE(entitate, an, luna, cont) index no
   longer carries ``ON CONFLICT REPLACE``. The import now does an explicit
   full-replace (DELETE the entity+period, then plain INSERT) in one
   transaction, so ghost rows for accounts that vanished from a corrected
   balance are removed. SQLite cannot ALTER a constraint, hence the rebuild.

2. Extend ``pnl_import_log`` with:
   - ``replaced INTEGER`` — how many rows the import deleted before inserting.
   - ``validari TEXT`` — JSON blob with the echilibru / inlantuire /
     reconciliere_121 validation results computed at import time.
"""

VERSION = 40
NAME = "0040_20260708_pnl_full_replace"


def up(conn):
    conn.executescript("""
        CREATE TABLE pnl_balante_raw_new (
            id          INTEGER PRIMARY KEY,
            source_file TEXT,
            entitate    TEXT,
            an          INTEGER,
            luna        INTEGER,
            cont        TEXT,
            dencont     TEXT,
            sid  REAL, sic  REAL, sfd  REAL, sfc  REAL,
            rulld REAL, rullc REAL, rulcd REAL, rulcc REAL,
            UNIQUE(entitate, an, luna, cont)
        );
        INSERT INTO pnl_balante_raw_new SELECT * FROM pnl_balante_raw;
        DROP TABLE pnl_balante_raw;
        ALTER TABLE pnl_balante_raw_new RENAME TO pnl_balante_raw;
    """)

    cols = [r[1] for r in conn.execute("PRAGMA table_info(pnl_import_log)")]
    if 'replaced' not in cols:
        conn.execute("ALTER TABLE pnl_import_log ADD COLUMN replaced INTEGER DEFAULT 0")
    if 'validari' not in cols:
        conn.execute("ALTER TABLE pnl_import_log ADD COLUMN validari TEXT")
