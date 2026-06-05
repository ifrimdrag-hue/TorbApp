"""Migration 0006 — Shopify sync history tables."""

VERSION = 6
NAME = "0006_20260605_shopify_sync_log"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS shopify_sync_sessions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_at   TEXT    NOT NULL,
            filename  TEXT
        );

        CREATE TABLE IF NOT EXISTS shopify_sync_rows (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          INTEGER NOT NULL REFERENCES shopify_sync_sessions(id),
            inventory_item_id   TEXT,
            sku                 TEXT,
            name                TEXT,
            old_stock           INTEGER,
            new_stock           INTEGER,
            status              TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_sync_rows_session ON shopify_sync_rows (session_id);
    """)
