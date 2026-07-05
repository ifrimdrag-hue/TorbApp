"""Migration 0021 - solduri_neincasate (accounts-receivable snapshot).

One row per open ERP document (invoice/advance). Replace-only: each import
truncates and reinserts. Due date is derived on read (datadl + term_pl_cl),
never taken from the file's `scadenta` column (which only holds the term).
"""

VERSION = 21
NAME = "0021_20260705_solduri_neincasate"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS solduri_neincasate (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            data_raport TEXT NOT NULL,
            nrdl        TEXT,
            datadl      TEXT,
            term_pl_cl  INTEGER,
            plafon      REAL,
            numecli     TEXT,
            codcli      TEXT,
            cfcli       TEXT,
            vtdl        REAL,
            sumdeincas  REAL,
            factout     TEXT,
            numeag      TEXT,
            canal       TEXT,
            telefon     TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_solduri_codcli ON solduri_neincasate(codcli);
        CREATE INDEX IF NOT EXISTS idx_solduri_agent  ON solduri_neincasate(numeag);
    """)
