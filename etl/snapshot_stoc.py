"""Capture a daily stock snapshot into `stock_snapshot` for OOS history.

The forecast out-of-stock correction (Brief §4.1, level 2) needs a per-day
record of what was on hand, so a month where an article was unavailable can be
told apart from a month of genuine zero demand. This copies the latest `stoc`
snapshot into `stock_snapshot`, one row per SKU, idempotent per date.

    python etl/snapshot_stoc.py            # snapshot the latest stoc date

PERSISTENCE: the ~daily rebuild (`etl/rebuild_db.py`) is partial — it drops only
`tranzactii`, `stoc`, and the views, so `stock_snapshot` SURVIVES a rebuild
(only the forecast `--reset` path drops it). What's needed is simply to RUN this
after each rebuild so a fresh dated snapshot is captured; wiring it as a step in
`rebuild_db.main()` (or a scheduled job) is the open item, not data loss. See
docs/plans/2026-07-04-forecast-spec-completion.md §C.
"""
import sqlite3
import sys

DB_PATH = "data/torb.db"


def capture(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT MAX(data_snapshot) AS d FROM stoc").fetchone()
        snap_date = row["d"] if row else None
        if not snap_date:
            print("No stoc snapshot to capture.")
            return 0

        exists = conn.execute(
            "SELECT 1 FROM stock_snapshot WHERE snapshot_date = ? LIMIT 1",
            (snap_date,),
        ).fetchone()
        if exists:
            print(f"stock_snapshot already has {snap_date}; nothing to do.")
            return 0

        rows = conn.execute(
            """
            SELECT MAX(cod_produs) AS cod_produs, sku, MAX(furnizor) AS furnizor,
                   SUM(cantitate) AS on_hand
            FROM stoc
            WHERE data_snapshot = ?
            GROUP BY sku
            """,
            (snap_date,),
        ).fetchall()

        conn.executemany(
            """
            INSERT INTO stock_snapshot
                (cod_produs, sku, furnizor, stock_on_hand, stock_on_order,
                 snapshot_date)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            [(r["cod_produs"], r["sku"], r["furnizor"], r["on_hand"] or 0,
              snap_date) for r in rows],
        )
        conn.commit()
        print(f"Captured {len(rows)} SKU rows for {snap_date}.")
        return len(rows)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(0 if capture() >= 0 else 1)
