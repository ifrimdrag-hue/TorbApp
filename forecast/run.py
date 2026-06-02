"""End-to-end forecasting pipeline + persistence.

CLI:
    python -m forecast.run                      # all brands in brands_config
    python -m forecast.run --brand Basilur      # single brand
    python -m forecast.run --horizon 24         # override horizon
    python -m forecast.run --all                # same as no brand

Writes rows to:
    forecast_runs         (1 row per run)
    forecasts             (1 row per SKU × canal × week)
    reorder_suggestions   (1 row per SKU needing action)
"""

import argparse
import hashlib
import os
import sqlite3
import traceback
from datetime import datetime

import pandas as pd

from forecast.data import weekly_brand_channel, sku_mix_recent
from forecast.hierarchy import allocate_to_sku
from forecast.models import (apply_overlays, compute_q4_multipliers,
                             compute_summer_dampener, fit_and_forecast)
from forecast.reorder import compute_reorder
from forecast.schema import DB_PATH, init_schema

LOCK_FILE = os.path.join(os.path.dirname(DB_PATH), ".forecast.lock")


def _acquire_lock():
    """Create lock file; returns False if another run is active."""
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()}\n{datetime.now().isoformat()}".encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _release_lock():
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass


def _input_hash(df):
    """Stable hash over input rows to detect upstream changes between runs."""
    m = hashlib.sha1()
    m.update(f"{len(df)}".encode())
    m.update(pd.util.hash_pandas_object(df[["unique_id", "ds", "y"]],
                                         index=False).values.tobytes())
    return m.hexdigest()[:16]


def _insert_run(conn, status, horizon, brands, error=None, input_hash=None):
    cur = conn.execute(
        """INSERT INTO forecast_runs
           (started_at, status, horizon_weeks, brands_included, error, input_hash)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), status, horizon,
         ",".join(brands), error, input_hash),
    )
    conn.commit()
    return cur.lastrowid


def _finish_run(conn, run_id, status, error=None):
    conn.execute(
        """UPDATE forecast_runs
           SET finished_at = ?, status = ?, error = ?
           WHERE run_id = ?""",
        (datetime.now().isoformat(), status, error, run_id),
    )
    conn.commit()


def _persist_forecasts(conn, run_id, sku_fc):
    if sku_fc.empty:
        return 0
    rows = []
    for r in sku_fc.itertuples(index=False):
        rows.append((run_id, r.cod_produs, r.sku, r.furnizor, r.canal,
                     pd.Timestamp(r.ds).date().isoformat(), r.method,
                     float(r.yhat), float(r.yhat_lo), float(r.yhat_hi)))
    conn.executemany(
        """INSERT OR REPLACE INTO forecasts
           (run_id, cod_produs, sku, furnizor, canal, week_start,
            method, yhat, yhat_lo, yhat_hi)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return len(rows)


def _persist_reorder(conn, run_id, reorder_df):
    if reorder_df.empty:
        return 0
    rows = []
    for r in reorder_df.itertuples(index=False):
        rows.append((run_id, r.cod_produs, r.sku, r.furnizor,
                     None if r.stock_on_hand is None else float(r.stock_on_hand),
                     float(r.demand_over_lead_time), float(r.safety_stock),
                     float(r.reorder_point), float(r.suggested_qty),
                     r.order_by_date, r.rationale, r.urgency))
    conn.executemany(
        """INSERT OR REPLACE INTO reorder_suggestions
           (run_id, cod_produs, sku, furnizor, stock_on_hand,
            demand_over_lead_time, safety_stock, reorder_point,
            suggested_qty, order_by_date, rationale, urgency)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return len(rows)


def _get_stock(conn):
    return pd.read_sql_query(
        "SELECT cod_produs, stock_on_hand, stock_on_order, snapshot_date "
        "FROM stock_snapshot", conn,
    )


def _get_config(conn, brands=None):
    sql = "SELECT * FROM brands_config"
    params = {}
    if brands:
        placeholders = ",".join(f":b{i}" for i in range(len(brands)))
        sql += f" WHERE furnizor IN ({placeholders})"
        for i, b in enumerate(brands):
            params[f"b{i}"] = b
    return pd.read_sql_query(sql, conn, params=params)


def run_pipeline(brands=None, horizon_weeks=20, db_path=DB_PATH,
                 mix_weeks=12):
    """Run forecast for one or more brands. Returns run_id."""
    init_schema(db_path)

    if not _acquire_lock():
        raise RuntimeError(
            f"Another forecast run is in progress (lock: {LOCK_FILE}). "
            "Remove the lock file if the previous run crashed."
        )

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        cfg = _get_config(conn, brands)
        if cfg.empty:
            raise ValueError(
                f"No brands matched in brands_config. "
                f"Requested: {brands}. Seed the table via forecast.schema."
            )
        brand_list = cfg["furnizor"].tolist()

        run_id = _insert_run(conn, "running", horizon_weeks, brand_list)
        total_fc = 0
        total_reorder = 0
        input_hashes = []

        for furnizor in brand_list:
            print(f"[{furnizor}] loading weekly series ...", flush=True)
            series = weekly_brand_channel(furnizor, db_path=db_path)
            if series.empty:
                print(f"[{furnizor}] no data; skipping", flush=True)
                continue
            input_hashes.append(_input_hash(series))

            print(f"[{furnizor}] computing overlays ...", flush=True)
            q4 = compute_q4_multipliers(series)
            summer_brands = []
            row = cfg[cfg["furnizor"] == furnizor].iloc[0]
            if row["summer_restriction"]:
                summer_brands.append(furnizor)
            summer = compute_summer_dampener(series, dampen_brands=summer_brands)

            print(f"[{furnizor}] fitting ETS on {series['unique_id'].nunique()} "
                  f"brand×canal series ...", flush=True)
            fc = fit_and_forecast(series, horizon_weeks=horizon_weeks)
            if fc.empty:
                print(f"[{furnizor}] forecast empty; skipping", flush=True)
                continue
            static = series[["unique_id", "furnizor", "canal"]].drop_duplicates()
            brand_fc = apply_overlays(fc.merge(static, on="unique_id"),
                                       q4, summer)

            print(f"[{furnizor}] loading SKU mix ({mix_weeks} weeks) ...",
                  flush=True)
            mix = sku_mix_recent(furnizor, weeks=mix_weeks, db_path=db_path)
            if mix.empty:
                print(f"[{furnizor}] no SKU mix; skipping", flush=True)
                continue

            print(f"[{furnizor}] allocating brand → {mix['cod_produs'].nunique()} "
                  "SKUs ...", flush=True)
            sku_fc = allocate_to_sku(brand_fc, mix)

            print(f"[{furnizor}] computing reorder ...", flush=True)
            stock = _get_stock(conn)
            cfg_one = cfg[cfg["furnizor"] == furnizor]
            reorder_df = compute_reorder(sku_fc, stock, cfg_one)

            inserted_fc = _persist_forecasts(conn, run_id, sku_fc)
            inserted_ro = _persist_reorder(conn, run_id, reorder_df)
            print(f"[{furnizor}] persisted {inserted_fc} forecast rows, "
                  f"{inserted_ro} reorder rows", flush=True)
            total_fc += inserted_fc
            total_reorder += inserted_ro

        combined_hash = hashlib.sha1("|".join(input_hashes).encode()).hexdigest()[:16]
        conn.execute(
            "UPDATE forecast_runs SET input_hash = ? WHERE run_id = ?",
            (combined_hash, run_id),
        )
        _finish_run(conn, run_id, "done")
        print(f"\nrun #{run_id} complete — {total_fc} forecasts, "
              f"{total_reorder} reorder rows", flush=True)
        return run_id

    except Exception as exc:
        tb = traceback.format_exc()
        try:
            _finish_run(conn, run_id, "failed", error=tb[-500:])
        except Exception:
            pass
        print(f"FAILED: {exc}", flush=True)
        print(tb, flush=True)
        raise
    finally:
        conn.close()
        _release_lock()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brand", help="run only this brand (repeatable)",
                        action="append")
    parser.add_argument("--all", action="store_true", help="run all brands")
    parser.add_argument("--horizon", type=int, default=20,
                        help="forecast horizon in weeks (default: 20)")
    parser.add_argument("--mix-weeks", type=int, default=12,
                        help="rolling window for SKU share allocation")
    args = parser.parse_args()

    brands = args.brand if args.brand else None
    run_id = run_pipeline(brands=brands, horizon_weeks=args.horizon,
                           mix_weeks=args.mix_weeks)
    print(f"run_id = {run_id}")


if __name__ == "__main__":
    main()
