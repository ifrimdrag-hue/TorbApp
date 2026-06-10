"""Middle-out allocation: brand × canal forecast → SKU × canal forecast.

Brand × canal forecasts are stable. Per-SKU weekly forecasts are noisy or
all-zero. We forecast at the stable level and allocate to SKUs by their
trailing 12-week share within the same (brand, canal) bucket, then
reconcile so the sum of SKU forecasts equals the brand × canal forecast.
"""

import pandas as pd


def allocate_to_sku(brand_forecast, mix):
    """Allocate brand × canal forecast to SKU × canal.

    brand_forecast: DataFrame with columns
        unique_id (brand|canal), ds, yhat, yhat_lo, yhat_hi, method,
        furnizor, canal.
    mix: DataFrame with columns (cod_produs, sku, furnizor, canal, share).

    Returns DataFrame with columns
        cod_produs, sku, furnizor, canal, ds, yhat, yhat_lo, yhat_hi, method.
    Sums per (furnizor, canal, ds) equal the brand × canal forecast.
    """
    if brand_forecast.empty or mix.empty:
        return pd.DataFrame(columns=[
            "cod_produs", "sku", "furnizor", "canal",
            "ds", "yhat", "yhat_lo", "yhat_hi", "method",
        ])

    # Join: every forecast row matches multiple SKU rows inside the same (furnizor, canal).
    merged = brand_forecast.merge(
        mix[["cod_produs", "sku", "furnizor", "canal", "share"]],
        on=["furnizor", "canal"],
        how="inner",
    )

    for col in ("yhat", "yhat_lo", "yhat_hi"):
        merged[col] = merged[col] * merged["share"]

    # Reconciliation check: recompute the share-sum per (furnizor, canal) and
    # redistribute any mass lost due to rounding. In practice statsforecast
    # output is exact, so this is a safety net.
    sums = (merged.groupby(["furnizor", "canal", "ds"], as_index=False)["yhat"]
                  .sum()
                  .rename(columns={"yhat": "sum_after"}))
    targets = brand_forecast[["furnizor", "canal", "ds", "yhat"]].rename(
        columns={"yhat": "target"}
    )
    check = sums.merge(targets, on=["furnizor", "canal", "ds"], how="left")
    import numpy as np
    safe_sum = check["sum_after"].replace(0, np.nan)
    check["scale"] = (check["target"] / safe_sum).fillna(1.0).astype(float)

    merged = merged.merge(
        check[["furnizor", "canal", "ds", "scale"]],
        on=["furnizor", "canal", "ds"], how="left",
    )
    for col in ("yhat", "yhat_lo", "yhat_hi"):
        merged[col] = merged[col] * merged["scale"]
    merged = merged.drop(columns=["scale", "share", "unique_id"])

    return merged[["cod_produs", "sku", "furnizor", "canal",
                   "ds", "yhat", "yhat_lo", "yhat_hi", "method"]]


def aggregate_to_monthly(sku_forecast):
    """Weekly SKU × canal → monthly SKU × canal (for cashflow/budget views).

    Weeks that straddle month boundaries are assigned to the month of their
    week_start (Monday).
    """
    if sku_forecast.empty:
        return sku_forecast

    df = sku_forecast.copy()
    df["ds"] = pd.to_datetime(df["ds"])
    df["month_start"] = df["ds"].dt.to_period("M").dt.start_time
    agg = (df.groupby(["cod_produs", "sku", "furnizor", "canal",
                        "month_start", "method"], as_index=False)
              .agg(yhat=("yhat", "sum"),
                   yhat_lo=("yhat_lo", "sum"),
                   yhat_hi=("yhat_hi", "sum")))
    return agg.rename(columns={"month_start": "ds"})


if __name__ == "__main__":
    from forecast.data import weekly_brand_channel, sku_mix_recent
    from forecast.models import (fit_and_forecast, compute_q4_multipliers,
                                 compute_summer_dampener, apply_overlays)

    df = weekly_brand_channel("Basilur")
    q4 = compute_q4_multipliers(df)
    summer = compute_summer_dampener(df)

    fc = fit_and_forecast(df, horizon_weeks=20)
    static = df[["unique_id", "furnizor", "canal"]].drop_duplicates()
    brand_fc = apply_overlays(fc.merge(static, on="unique_id"), q4, summer)

    mix = sku_mix_recent("Basilur", weeks=12)
    print(f"brand forecast: {len(brand_fc)} rows, "
          f"mix: {len(mix)} SKU-canal combos")

    sku_fc = allocate_to_sku(brand_fc, mix)
    print(f"\nsku forecast: {len(sku_fc)} rows, "
          f"distinct SKUs: {sku_fc['cod_produs'].nunique()}")

    # Reconciliation check
    brand_totals = brand_fc.groupby(["furnizor", "canal", "ds"])["yhat"].sum()
    sku_totals = sku_fc.groupby(["furnizor", "canal", "ds"])["yhat"].sum()
    diff = (brand_totals - sku_totals).abs().max()
    print(f"reconciliation max abs diff: {diff:.4f} (should be ~0)")

    print("\nMonthly aggregation:")
    monthly = aggregate_to_monthly(sku_fc)
    print(f"monthly: {len(monthly)} rows")
    print(monthly.head(3))
