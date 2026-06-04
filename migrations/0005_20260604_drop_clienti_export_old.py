"""Migration 0005 — drop orphan table clienti_export_old."""

VERSION = 5
NAME = "0005_20260604_drop_clienti_export_old"


def up(conn):
    conn.execute("DROP TABLE IF EXISTS clienti_export_old")
