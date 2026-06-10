"""Forecast module schema bootstrap.

Normal path: delegates to the versioned migration runner (migration 0004).
Reset path:  drops all forecast tables, removes version 4 from schema_version,
             then re-runs the runner so the tables are recreated fresh.

CLI usage (from project root):
    python -m forecast.schema            # ensure tables exist (idempotent)
    python -m forecast.schema --reset    # drop + recreate forecast tables
"""

import os
import sqlite3
import argparse
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DB_PATH = os.path.join(_ROOT, "data", "torb.db")

DROPS = [
    "DROP TABLE IF EXISTS reorder_suggestions",
    "DROP TABLE IF EXISTS forecast_backtests",
    "DROP TABLE IF EXISTS forecasts",
    "DROP TABLE IF EXISTS forecast_runs",
    "DROP TABLE IF EXISTS stock_snapshot",
    "DROP TABLE IF EXISTS brands_config",
]


def init_schema(db_path=DB_PATH, reset=False):
    from migrations.runner import run_all

    if reset:
        conn = sqlite3.connect(db_path)
        try:
            for stmt in DROPS:
                conn.execute(stmt)
            conn.execute("DELETE FROM schema_version WHERE version = 4")
            conn.commit()
        finally:
            conn.close()

    run_all(db_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop + recreate forecast tables")
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    init_schema(args.db, reset=args.reset)
    print(f"forecast schema ready at {args.db}")


if __name__ == "__main__":
    main()
