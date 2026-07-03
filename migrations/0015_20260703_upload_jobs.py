"""
Migration 0015 - upload_jobs table for cross-worker import status.

The async file-upload endpoints tracked job status in a per-process
in-memory dict (_upload_jobs). Under multiple gunicorn workers (prod=3,
dev=2) a status poll could land on a worker that never saw the job and
wrongly report "server restarted". Persisting job state to SQLite lets
any worker answer the poll, and it survives a real restart.
"""

VERSION = 15
NAME = "0015_20260703_upload_jobs"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS upload_jobs (
            job_id        TEXT PRIMARY KEY,
            tip           TEXT,
            fisier        TEXT,
            status        TEXT NOT NULL,
            mesaj         TEXT,
            randuri       INTEGER,
            avertisment   TEXT,
            creat_la      TEXT DEFAULT (datetime('now','localtime')),
            actualizat_la TEXT DEFAULT (datetime('now','localtime'))
        );
    """)
