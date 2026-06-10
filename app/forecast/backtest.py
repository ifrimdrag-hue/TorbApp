"""Rolling-origin backtest for forecast models.

With 27 months = ~117 weeks we use 3 rolling-origin folds, horizon 13 weeks:

    fold 1:  train 0..(T-39)   → test (T-39)..(T-26)
    fold 2:  train 0..(T-26)   → test (T-26)..(T-13)
    fold 3:  train 0..(T-13)   → test (T-13)..T

Metrics:
    WAPE = Σ|y - yhat| / Σ|y|        (revenue-weighted when val_neta provided)
    MASE = mean(|y-yhat|) / mean(|y_t - y_{t-1}|)    (scale-free)
    bias = mean(y - yhat) / mean(|y|)
    service_level_achieved = 1 - stockout_rate
                             (fraction of weeks where actual > forecast)

CLI:
    python -m forecast.backtest --brand Basilur
    python -m forecast.backtest --all
"""

import argparse
import sqlite3
import numpy as np
import pandas as pd

from .data import weekly_brand_channel
from .models import (apply_overlays, compute_q4_multipliers,
                     compute_summer_dampener, fit_and_forecast)
from .schema import DB_PATH


def _wape(y_true, y_pred):
    total = np.abs(y_true).sum()
    if total == 0:
        return np.nan
    return float(np.abs(y_true - y_pred).sum() / total)


def _mase(y_true, y_pred):
    if len(y_true) < 2:
        return np.nan
    naive_diff = np.abs(np.diff(y_true)).mean()
    if naive_diff == 0:
        return np.nan
    return float(np.abs(y_true - y_pred).mean() / naive_diff)


def _bias(y_true, y_pred):
    total = np.abs(y_true).sum()
    if total == 0:
        return np.nan
    return float((y_true - y_pred).mean() / np.abs(y_true).mean())


def _service_level(y_true, y_pred):
    if len(y_true) == 0:
        return np.nan
    # % of weeks where actual <= forecast (customer demand was covered by plan)
    return float((y_true <= y_pred).mean())


def run_backtest(furnizor, horizon_weeks=13, folds=3):
    """Return DataFrame of fold-level metrics for a single brand.

    Aggregates at brand × canal level for WAPE/MASE/bias (meaningful scale).
    """
    series = weekly_brand_channel(furnizor)
    if series.empty:
        return pd.DataFrame()

    weeks = sorted(series["ds"].unique())
    T = len(weeks)
    if T < horizon_weeks * (folds + 1):
        print(f"[{furnizor}] insufficient history ({T} weeks); "
              f"need ≥{horizon_weeks * (folds + 1)}")
        return pd.DataFrame()

    metrics_rows = []

    for fold in range(1, folds + 1):
        split = T - (folds - fold + 1) * horizon_weeks
        train = series[series["ds"] <= weeks[split - 1]]
        test  = series[(series["ds"] > weeks[split - 1]) &
                       (series["ds"] <= weeks[min(split + horizon_weeks - 1, T - 1)])]
        if train.empty or test.empty:
            continue

        # Overlays computed per-fold on training data only — no leakage.
        q4_f = compute_q4_multipliers(train)
        summer_f = compute_summer_dampener(
            train,
            dampen_brands=[furnizor] if furnizor in ("Toras", "Delaviuda") else [],
        )

        fc = fit_and_forecast(train[["unique_id", "ds", "y"]],
                               horizon_weeks=horizon_weeks)
        static = train[["unique_id", "furnizor", "canal"]].drop_duplicates()
        fc = apply_overlays(fc.merge(static, on="unique_id"), q4_f, summer_f)

        merged = test.merge(fc[["unique_id", "ds", "yhat"]],
                             on=["unique_id", "ds"], how="inner")
        if merged.empty:
            continue

        # Brand-level aggregation (sum across canals) for WAPE/bias.
        brand_grp = (merged.groupby("ds", as_index=False)
                            .agg(y=("y", "sum"), yhat=("yhat", "sum")))

        metrics_rows.append({
            "level": "brand",
            "entity": furnizor,
            "fold": fold,
            "wape": _wape(brand_grp["y"].values, brand_grp["yhat"].values),
            "mase": _mase(brand_grp["y"].values, brand_grp["yhat"].values),
            "bias": _bias(brand_grp["y"].values, brand_grp["yhat"].values),
            "service_level_achieved": _service_level(
                brand_grp["y"].values, brand_grp["yhat"].values),
        })

        # Canal-level
        for canal, grp in merged.groupby("canal"):
            y = grp["y"].values
            yh = grp["yhat"].values
            metrics_rows.append({
                "level": "canal",
                "entity": f"{furnizor}|{canal}",
                "fold": fold,
                "wape": _wape(y, yh),
                "mase": _mase(y, yh),
                "bias": _bias(y, yh),
                "service_level_achieved": _service_level(y, yh),
            })

    return pd.DataFrame(metrics_rows)


def persist(df, db_path=DB_PATH, run_id=None):
    if df.empty:
        return 0
    with sqlite3.connect(db_path) as conn:
        if run_id is None:
            row = conn.execute(
                "SELECT MAX(run_id) FROM forecast_runs WHERE status='done'"
            ).fetchone()
            run_id = row[0] if row and row[0] else 0

        df = df.copy()
        df.insert(0, "run_id", run_id)
        conn.execute(
            "DELETE FROM forecast_backtests WHERE run_id = ?", (run_id,)
        )
        payload = [tuple(r) for r in df[[
            "run_id", "level", "entity", "fold",
            "wape", "mase", "bias", "service_level_achieved",
        ]].itertuples(index=False)]
        conn.executemany(
            """INSERT INTO forecast_backtests
               (run_id, level, entity, fold, wape, mase, bias,
                service_level_achieved)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            payload,
        )
        conn.commit()
    return len(df)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brand", action="append",
                        help="single brand; repeatable")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--horizon", type=int, default=13)
    parser.add_argument("--folds", type=int, default=3)
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()

    if args.brand:
        brands = args.brand
    else:
        with sqlite3.connect(DB_PATH) as conn:
            brands = [r[0] for r in conn.execute(
                "SELECT furnizor FROM brands_config ORDER BY furnizor"
            ).fetchall()]

    all_metrics = []
    for b in brands:
        print(f"\n=== backtest {b} (horizon={args.horizon}, folds={args.folds}) ===")
        df = run_backtest(b, args.horizon, args.folds)
        if df.empty:
            continue
        brand_rows = df[df["level"] == "brand"]
        print(brand_rows[["fold", "wape", "mase", "bias",
                           "service_level_achieved"]].to_string(index=False))
        print(f"  avg WAPE: {brand_rows['wape'].mean():.3f}")
        print(f"  avg bias: {brand_rows['bias'].mean():.3f}")
        print(f"  avg SL:   {brand_rows['service_level_achieved'].mean():.3f}")
        all_metrics.append(df)

    if all_metrics and not args.no_persist:
        combined = pd.concat(all_metrics, ignore_index=True)
        n = persist(combined)
        print(f"\npersisted {n} backtest rows")


if __name__ == "__main__":
    main()
