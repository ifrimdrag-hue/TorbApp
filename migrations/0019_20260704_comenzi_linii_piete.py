"""
Migration 0019 — per-country quantities on supplier-order lines.

Owner decision (2026-07-04, multi-country export model): order quantities are
persisted per country market (piata), not just displayed. The existing
cantitate_ro / cantitate_export columns remain as aggregates for reporting and
backward compatibility; this child table holds the per-piata breakdown.
"""

VERSION = 19
NAME = "0019_20260704_comenzi_linii_piete"

DDL = """
CREATE TABLE IF NOT EXISTS comenzi_linii_piete (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    linie_id  INTEGER NOT NULL REFERENCES comenzi_furnizori_linii(id) ON DELETE CASCADE,
    piata     TEXT    NOT NULL,
    cantitate INTEGER NOT NULL DEFAULT 0,
    UNIQUE (linie_id, piata)
)
"""


def up(conn):
    conn.execute(DDL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_comenzi_linii_piete_linie "
        "ON comenzi_linii_piete(linie_id)"
    )
