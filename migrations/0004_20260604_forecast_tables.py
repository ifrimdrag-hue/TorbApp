"""
Migration 0004 — forecast module tables and brand seeds.

Moves forecast schema management into the versioned migration runner so that
a fresh deploy gets all forecast tables automatically on Flask startup.

Creates: brands_config, stock_snapshot, forecast_runs, forecasts,
         forecast_backtests, reorder_suggestions (+ two indexes)
Seeds:   brands_config with 11 suppliers
"""

VERSION = 4
NAME = "0004_20260604_forecast_tables"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS brands_config (
            furnizor               TEXT PRIMARY KEY,
            lead_time_weeks        INTEGER NOT NULL,
            moq_units              INTEGER,
            target_service_level   REAL DEFAULT 0.98,
            review_period_weeks    INTEGER DEFAULT 1,
            summer_restriction     INTEGER DEFAULT 0,
            financed_by_supplier   INTEGER DEFAULT 0,
            notes                  TEXT
        );

        CREATE TABLE IF NOT EXISTS stock_snapshot (
            cod_produs      TEXT,
            sku             TEXT,
            furnizor        TEXT,
            stock_on_hand   REAL,
            stock_on_order  REAL,
            snapshot_date   TEXT,
            PRIMARY KEY (cod_produs, snapshot_date)
        );

        CREATE TABLE IF NOT EXISTS forecast_runs (
            run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at      TEXT,
            finished_at     TEXT,
            status          TEXT,
            horizon_weeks   INTEGER,
            brands_included TEXT,
            error           TEXT,
            input_hash      TEXT
        );

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
        );

        CREATE INDEX IF NOT EXISTS idx_forecasts_furnizor
            ON forecasts (furnizor, week_start);
        CREATE INDEX IF NOT EXISTS idx_forecasts_sku
            ON forecasts (cod_produs, week_start);

        CREATE TABLE IF NOT EXISTS forecast_backtests (
            run_id                 INTEGER,
            level                  TEXT,
            entity                 TEXT,
            fold                   INTEGER,
            wape                   REAL,
            mase                   REAL,
            bias                   REAL,
            service_level_achieved REAL
        );

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
        );
    """)

    seeds = [
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
    conn.executemany("""
        INSERT OR IGNORE INTO brands_config
            (furnizor, lead_time_weeks, moq_units, target_service_level,
             review_period_weeks, summer_restriction, financed_by_supplier, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, seeds)
