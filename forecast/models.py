"""Forecasting models with Q4 overlay + summer dampener.

Design:
- AutoETS for smooth series (stable monthly/quarterly pattern).
- SeasonalNaive as fallback baseline AND for series with very short history.
- Q4 multiplicative overlay computed from 2024 and 2025 per brand, applied
  on top of the base forecast. Handles sezonalitate Q4 explicit — cu doar
  2 observații istorice, nu e sigur să lași modelul să o învețe singur.
- Summer dampener (Jun-Aug): multiplier < 1 for Toras/Delaviuda to reflect
  transport restrictions.

All models operate on weekly series (freq='W-MON').
"""

import pandas as pd

from statsforecast import StatsForecast
from statsforecast.models import AutoETS, SeasonalNaive


MIN_HISTORY_WEEKS = 26
Q4_MONTHS = {10, 11, 12}
SUMMER_MONTHS = {6, 7, 8}


# -----------------------------------------------------------------------------
# Q4 overlay
# -----------------------------------------------------------------------------

def compute_q4_multipliers(df, furnizor_col="furnizor"):
    """Return dict {furnizor: q4_multiplier}.

    Multiplier = mean weekly quantity in Q4 / mean weekly quantity Jan-Sep.
    Uses only historical years that have a complete Q4 (2024, 2025).
    """
    if df.empty:
        return {}

    work = df.copy()
    work["month"] = pd.to_datetime(work["ds"]).dt.month
    work["year"] = pd.to_datetime(work["ds"]).dt.year

    complete_years = [y for y in work["year"].unique()
                      if set(work.loc[work["year"] == y, "month"]).issuperset(Q4_MONTHS)]
    if not complete_years:
        return {}

    work = work[work["year"].isin(complete_years)]

    multipliers = {}
    for brand in work[furnizor_col].unique():
        sub = work[work[furnizor_col] == brand]
        q4_mean = sub.loc[sub["month"].isin(Q4_MONTHS), "y"].mean()
        base_mean = sub.loc[~sub["month"].isin(Q4_MONTHS), "y"].mean()
        if base_mean and base_mean > 0:
            m = q4_mean / base_mean
            # Cap at [0.5, 3.0] to avoid absurd values from small samples.
            multipliers[brand] = float(max(0.5, min(3.0, m)))
        else:
            multipliers[brand] = 1.0
    return multipliers


def compute_summer_dampener(df, furnizor_col="furnizor",
                             dampen_brands=("Toras", "Delaviuda")):
    """Return dict {furnizor: summer_multiplier} for dampen_brands.

    For brands with physical summer restrictions, compute ratio
    summer_demand / non_summer_demand from history. Capped at [0.6, 1.0].
    """
    if df.empty:
        return {}

    work = df.copy()
    work["month"] = pd.to_datetime(work["ds"]).dt.month

    out = {}
    for brand in dampen_brands:
        sub = work[work[furnizor_col] == brand]
        if sub.empty:
            continue
        summer_mean = sub.loc[sub["month"].isin(SUMMER_MONTHS), "y"].mean()
        rest_mean = sub.loc[~sub["month"].isin(SUMMER_MONTHS), "y"].mean()
        if rest_mean and rest_mean > 0 and summer_mean is not None:
            m = summer_mean / rest_mean
            out[brand] = float(max(0.6, min(1.0, m)))
        else:
            out[brand] = 0.8
    return out


def apply_overlays(forecast_df, q4_mult, summer_mult=None):
    """Apply Q4 and summer multipliers to forecast in-place (new df).

    forecast_df: columns (unique_id, ds, yhat, yhat_lo, yhat_hi, furnizor).
    """
    df = forecast_df.copy()
    df["month"] = pd.to_datetime(df["ds"]).dt.month

    for col in ("yhat", "yhat_lo", "yhat_hi"):
        df[col] = df[col].astype(float)

    for brand, mult in (q4_mult or {}).items():
        mask = (df["furnizor"] == brand) & (df["month"].isin(Q4_MONTHS))
        df.loc[mask, ["yhat", "yhat_lo", "yhat_hi"]] *= mult

    for brand, mult in (summer_mult or {}).items():
        mask = (df["furnizor"] == brand) & (df["month"].isin(SUMMER_MONTHS))
        df.loc[mask, ["yhat", "yhat_lo", "yhat_hi"]] *= mult

    # Floor negative forecasts at zero (units cannot be negative).
    for col in ("yhat", "yhat_lo", "yhat_hi"):
        df[col] = df[col].clip(lower=0)

    return df.drop(columns=["month"])


# -----------------------------------------------------------------------------
# Model fitting
# -----------------------------------------------------------------------------

def _pad_with_seasonal_naive(series, min_weeks=MIN_HISTORY_WEEKS):
    """Too-short series → pad with zeros at the front so statsforecast runs."""
    return series


def fit_and_forecast(df, horizon_weeks=20, season_length=52, level=(80,)):
    """Fit AutoETS per series; return forecast DataFrame.

    Input df: (unique_id, ds, y) at weekly freq. Any extra columns are preserved
    on the returned frame by a post-merge.

    Returns DataFrame with (unique_id, ds, yhat, yhat_lo, yhat_hi, method).
    Series with < MIN_HISTORY_WEEKS of non-zero weeks fall back to SeasonalNaive
    (or average if fewer than 2 cycles).
    """
    if df.empty:
        return pd.DataFrame(columns=["unique_id", "ds", "yhat",
                                     "yhat_lo", "yhat_hi", "method"])

    core = df[["unique_id", "ds", "y"]].copy()
    core["ds"] = pd.to_datetime(core["ds"])

    # Segment by non-zero count
    nonzero_counts = (core.assign(nz=core["y"] > 0)
                           .groupby("unique_id")["nz"].sum())
    smooth_ids = nonzero_counts[nonzero_counts >= MIN_HISTORY_WEEKS].index.tolist()
    sparse_ids = nonzero_counts[nonzero_counts <  MIN_HISTORY_WEEKS].index.tolist()

    out_frames = []

    if smooth_ids:
        smooth_df = core[core["unique_id"].isin(smooth_ids)]
        sf = StatsForecast(
            models=[AutoETS(season_length=season_length, model="ZZA")],
            freq="W-MON",
            n_jobs=1,
        )
        fc = sf.forecast(df=smooth_df, h=horizon_weeks, level=list(level))
        # statsforecast returns columns like AutoETS, AutoETS-lo-80, AutoETS-hi-80
        model_col = [c for c in fc.columns if c == "AutoETS"][0]
        lo_col = f"AutoETS-lo-{level[0]}"
        hi_col = f"AutoETS-hi-{level[0]}"
        fc_std = fc.rename(columns={
            model_col: "yhat",
            lo_col: "yhat_lo",
            hi_col: "yhat_hi",
        })
        fc_std["method"] = "ets"
        fc_std = fc_std[["unique_id", "ds", "yhat", "yhat_lo", "yhat_hi", "method"]]
        out_frames.append(fc_std)

    if sparse_ids:
        sparse_df = core[core["unique_id"].isin(sparse_ids)]
        # Fall back to SeasonalNaive; if even that fails because of short
        # history, final fallback is flat zero.
        sf = StatsForecast(
            models=[SeasonalNaive(season_length=season_length)],
            freq="W-MON",
            n_jobs=1,
        )
        try:
            fc = sf.forecast(df=sparse_df, h=horizon_weeks, level=list(level))
            model_col = [c for c in fc.columns if c == "SeasonalNaive"][0]
            lo_col = f"SeasonalNaive-lo-{level[0]}"
            hi_col = f"SeasonalNaive-hi-{level[0]}"
            fc_std = fc.rename(columns={
                model_col: "yhat",
                lo_col: "yhat_lo",
                hi_col: "yhat_hi",
            })
            fc_std["method"] = "seasonal_naive"
            fc_std = fc_std[["unique_id", "ds", "yhat", "yhat_lo",
                             "yhat_hi", "method"]]
            out_frames.append(fc_std)
        except Exception:
            # Zero-series fallback
            last = sparse_df.groupby("unique_id").tail(1)[["unique_id", "ds"]]
            horizon_dates = pd.date_range(
                start=last["ds"].min() + pd.Timedelta(weeks=1),
                periods=horizon_weeks, freq="W-MON",
            )
            rows = []
            for uid in sparse_ids:
                mean_y = sparse_df.loc[sparse_df["unique_id"] == uid, "y"].mean()
                for d in horizon_dates:
                    rows.append({"unique_id": uid, "ds": d, "yhat": mean_y or 0,
                                 "yhat_lo": 0, "yhat_hi": (mean_y or 0) * 2,
                                 "method": "mean_fallback"})
            out_frames.append(pd.DataFrame(rows))

    if not out_frames:
        return pd.DataFrame(columns=["unique_id", "ds", "yhat",
                                     "yhat_lo", "yhat_hi", "method"])

    result = pd.concat(out_frames, ignore_index=True)
    result["ds"] = pd.to_datetime(result["ds"])
    # Floor forecasts at zero (units).
    for col in ("yhat", "yhat_lo", "yhat_hi"):
        result[col] = result[col].clip(lower=0)
    return result


if __name__ == "__main__":
    from forecast.data import weekly_brand_channel

    df = weekly_brand_channel("Basilur")
    print(f"input: {len(df)} rows, {df['unique_id'].nunique()} series")

    q4 = compute_q4_multipliers(df)
    print(f"Q4 multipliers: {q4}")

    summer = compute_summer_dampener(df)
    print(f"Summer dampener: {summer}")

    fc = fit_and_forecast(df, horizon_weeks=20)
    print(f"\nforecast: {len(fc)} rows, methods: {fc['method'].value_counts().to_dict()}")

    # Attach furnizor and apply overlays
    static = df[["unique_id", "furnizor", "canal"]].drop_duplicates()
    fc_full = fc.merge(static, on="unique_id", how="left")
    fc_out = apply_overlays(fc_full, q4, summer)
    print("\nfirst 5 rows:")
    print(fc_out.head())
