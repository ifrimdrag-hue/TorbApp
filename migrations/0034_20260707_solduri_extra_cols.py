"""Migration 0034 — extra columns on solduri_neincasate.

The richer ERP export carries discount and cheque (CEC) fields: discount %,
CEC flag, CEC due date, and the CEC-associated document no. Replace-only
table, so no backfill — the next import repopulates every row.
"""

VERSION = 34
NAME = "0034_20260707_solduri_extra_cols"


def up(conn):
    conn.executescript("""
        ALTER TABLE solduri_neincasate ADD COLUMN discount REAL;
        ALTER TABLE solduri_neincasate ADD COLUMN cec      INTEGER;
        ALTER TABLE solduri_neincasate ADD COLUMN scad_cec TEXT;
        ALTER TABLE solduri_neincasate ADD COLUMN cec_doc  TEXT;
    """)
