"""
Migration 0020 — drop the CHECK(piata IN ('RO','HU')) constraint on tari_export.

The multi-country export model (migration 0019 + owner item 2) makes piata a
free short market code (BG, AT, MD, ...), but the original 0001 DDL only
allowed RO/HU, so adding any new country failed at the DB level. SQLite cannot
drop a CHECK constraint in place — rebuild the table (same columns, same ids)
without it.

FK note: clienti_export.tara_id references tari_export(id). Enforcement is
disabled for the rebuild (the PRAGMA runs before any DML opens a transaction);
ids are preserved so child rows stay valid.
"""

VERSION = 20
NAME = "0020_20260704_tari_export_free_piata"


def up(conn):
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("""
        CREATE TABLE tari_export_new (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tara       TEXT NOT NULL UNIQUE,
            piata      TEXT NOT NULL DEFAULT 'HU',
            activ      INTEGER DEFAULT 1,
            observatii TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT INTO tari_export_new (id, tara, piata, activ, observatii, created_at)
        SELECT id, tara, piata, activ, observatii, created_at FROM tari_export
    """)
    conn.execute("DROP TABLE tari_export")
    conn.execute("ALTER TABLE tari_export_new RENAME TO tari_export")
