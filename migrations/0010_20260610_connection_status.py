"""Migration 0010 — connection_status cache table (eMAG/Shopify connDot)."""

VERSION = 10
NAME = "0010_20260610_connection_status"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS connection_status (
            platform    TEXT PRIMARY KEY,
            ok          INTEGER NOT NULL,
            payload     TEXT,
            checked_at  TEXT NOT NULL
        );
    """)
