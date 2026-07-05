"""Migration 0025 - price proposals (pricing module F2 simulator).

A proposal is a saved simulation for one client: proposed prices per SKU
with the net margin and threshold verdict computed server-side at save time.
"""

VERSION = 25
NAME = "0025_20260706_propuneri_pret"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS propuneri_pret (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            an          INTEGER NOT NULL,
            cod_client  TEXT NOT NULL,
            titlu       TEXT,
            status      TEXT NOT NULL DEFAULT 'draft',
            creat_la    DATETIME DEFAULT (datetime('now','localtime')),
            actualizat_la DATETIME
        );
        CREATE TABLE IF NOT EXISTS propuneri_pret_linii (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            propunere_id  INTEGER NOT NULL REFERENCES propuneri_pret(id)
                          ON DELETE CASCADE,
            sku           TEXT NOT NULL,
            pret_actual   REAL,
            pret_propus   REAL NOT NULL,
            landing_ron   REAL,
            cond_pct      REAL,
            marja_neta_pct REAL,
            verdict       TEXT,
            UNIQUE(propunere_id, sku)
        );
        CREATE INDEX IF NOT EXISTS idx_prop_client
            ON propuneri_pret(cod_client, an);
    """)
