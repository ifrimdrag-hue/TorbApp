"""Forecast module SQLite schema + seeding.

Usage:
    python -m forecast.schema            # create tables + seed brands_config
    python -m forecast.schema --reset    # drop forecast tables and recreate

Idempotent: safe to re-run. Never touches tranzactii or bonus tables.
"""

import os
import sqlite3
import argparse

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "torb.db",
)

DDL = [
    """
    CREATE TABLE IF NOT EXISTS brands_config (
        furnizor               TEXT PRIMARY KEY,
        lead_time_weeks        INTEGER NOT NULL,
        moq_units              INTEGER,
        target_service_level   REAL DEFAULT 0.98,
        review_period_weeks    INTEGER DEFAULT 1,
        summer_restriction     INTEGER DEFAULT 0,
        financed_by_supplier   INTEGER DEFAULT 0,
        notes                  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_snapshot (
        cod_produs      TEXT,
        sku             TEXT,
        furnizor        TEXT,
        stock_on_hand   REAL,
        stock_on_order  REAL,
        snapshot_date   TEXT,
        PRIMARY KEY (cod_produs, snapshot_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS forecast_runs (
        run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at      TEXT,
        finished_at     TEXT,
        status          TEXT,
        horizon_weeks   INTEGER,
        brands_included TEXT,
        error           TEXT,
        input_hash      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS forecasts (
        run_id      INTEGER,
        cod_produs  TEXT,
        sku         TEXT,
        furnizor    TEXT,
        canal       TEXT,
        week_start  TEXT,
        method      TEXT,
        yhat        REAL,
        yhat_lo     REAL,
        yhat_hi     REAL,
        PRIMARY KEY (run_id, cod_produs, canal, week_start)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_forecasts_furnizor ON forecasts (furnizor, week_start)",
    "CREATE INDEX IF NOT EXISTS idx_forecasts_sku      ON forecasts (cod_produs, week_start)",
    """
    CREATE TABLE IF NOT EXISTS forecast_backtests (
        run_id                 INTEGER,
        level                  TEXT,
        entity                 TEXT,
        fold                   INTEGER,
        wape                   REAL,
        mase                   REAL,
        bias                   REAL,
        service_level_achieved REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reorder_suggestions (
        run_id                INTEGER,
        cod_produs            TEXT,
        sku                   TEXT,
        furnizor              TEXT,
        stock_on_hand         REAL,
        demand_over_lead_time REAL,
        safety_stock          REAL,
        reorder_point         REAL,
        suggested_qty         REAL,
        order_by_date         TEXT,
        rationale             TEXT,
        urgency               TEXT,
        PRIMARY KEY (run_id, cod_produs)
    )
    """,
]

DROPS = [
    "DROP TABLE IF EXISTS reorder_suggestions",
    "DROP TABLE IF EXISTS forecast_backtests",
    "DROP TABLE IF EXISTS forecasts",
    "DROP TABLE IF EXISTS forecast_runs",
    "DROP TABLE IF EXISTS stock_snapshot",
    "DROP TABLE IF EXISTS brands_config",
]

# Seeds for brands_config. Service level per tier:
#   99% — Basilur (4mo lead, supplier financing, catastrophic stockout)
#   98% — top brands (Toras, Leonex, Celmar)
#   95% — B-tier
#   90% — long-tail
# Lead times: Basilur 16 weeks (Sri Lanka import), others 4 weeks (~1 month).
SEEDS = [
    # furnizor, lead_wks, moq, SL, review, summer_restrict, financed, notes
    ("Basilur",   16, None, 0.99, 4, 0, 1, "Sri Lanka import; supplier financing; 4-month lead time"),
    ("Toras",      4, None, 0.98, 1, 1, 0, "Summer transport restriction (no cold storage)"),
    ("Leonex",     4, None, 0.98, 1, 0, 0, "Own brand"),
    ("Celmar",     4, None, 0.98, 1, 0, 0, "Own brand"),
    ("Delaviuda",  4, None, 0.98, 1, 1, 0, "Chocolate; summer transport restriction"),
    ("KingSLeaf",  4, None, 0.95, 1, 0, 0, None),
    ("Solvex",     4, None, 0.95, 1, 0, 0, None),
    ("Tipson",     4, None, 0.95, 1, 0, 0, None),
    ("Cosmetice",  4, None, 0.95, 1, 0, 0, None),
    ("Colian",     4, None, 0.95, 1, 0, 0, None),
    ("Foite",      4, None, 0.90, 1, 0, 0, None),
]

SEED_SQL = """
INSERT OR IGNORE INTO brands_config
    (furnizor, lead_time_weeks, moq_units, target_service_level,
     review_period_weeks, summer_restriction, financed_by_supplier, notes)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


def init_schema(db_path=DB_PATH, reset=False):
    conn = sqlite3.connect(db_path)
    try:
        if reset:
            for stmt in DROPS:
                conn.execute(stmt)
        for stmt in DDL:
            conn.execute(stmt)
        cur = conn.cursor()
        cur.executemany(SEED_SQL, SEEDS)
        conn.commit()
        seeded = cur.rowcount
        return seeded
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop + recreate tables")
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    seeded = init_schema(args.db, reset=args.reset)
    print(f"forecast schema ready at {args.db}")
    print(f"seeded {seeded} new rows into brands_config")


if __name__ == "__main__":
    main()
