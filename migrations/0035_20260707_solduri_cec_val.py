"""Migration 0035 — cheque value column on solduri_neincasate.

The invoice list surfaces the cheque amount allocated to each invoice
(sum across one or more cheques). Replace-only table, so no backfill —
the next import repopulates cec_val for every row.
"""

VERSION = 35
NAME = "0035_20260707_solduri_cec_val"


def up(conn):
    conn.executescript("""
        ALTER TABLE solduri_neincasate ADD COLUMN cec_val REAL;
    """)
