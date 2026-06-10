"""Migration 0009 — Rename sync history tables: shopify_ prefix obsolete since they became multi-platform."""

VERSION = 9
NAME = "0009_20260610_rename_sync_tables"


def up(conn):
    conn.executescript("""
        ALTER TABLE shopify_sync_sessions RENAME TO sync_sessions;
        ALTER TABLE shopify_sync_rows RENAME TO sync_rows;
    """)
