"""Migration 0007 — Add platform column to sync history tables."""

VERSION = 7
NAME = "0007_20260609_sync_platform_column"


def up(conn):
    conn.executescript("""
        ALTER TABLE shopify_sync_sessions ADD COLUMN platform TEXT NOT NULL DEFAULT 'shopify';
        ALTER TABLE shopify_sync_rows ADD COLUMN platform TEXT NOT NULL DEFAULT 'shopify';
    """)
