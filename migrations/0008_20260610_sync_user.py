"""Migration 0008 — Add user_id column to sync sessions (who performed the sync)."""

VERSION = 8
NAME = "0008_20260610_sync_user"


def up(conn):
    conn.executescript("""
        ALTER TABLE shopify_sync_sessions ADD COLUMN user_id INTEGER REFERENCES users(id);
    """)
