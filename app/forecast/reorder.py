"""Reorder point and suggested order computation.

Per-SKU policy (aggregated across canals within the same brand):

  demand_over_protection = Σ yhat over (lead_time + review_period) weeks
  safety_stock  = z * σ_weekly * sqrt(lead_time + review_period)
  reorder_point = demand_over_lead_time + safety_stock   # trigger level
  target_stock  = demand_over_protection + safety_stock   # order-up-to

  if stock_on_hand + stock_on_order < reorder_point:
      suggested_qty = max(0, target_stock - stock_on_hand - stock_on_order)
      round up to MOQ

Urgency:
  critical — stock_on_hand + on_order < safety_stock (stockout imminent)
  high     — stock < reorder_point but > safety_stock (order now)
  normal   — stock >= reorder_point (no action needed)

order_by_date: today + days_of_cover_remaining_above_safety_stock,
               truncated so it's never negative.
"""

import datetime as dt
import pandas as pd
from scipy.stats import norm


def _z_score(service_level):
    """Two-sided normal quantile for demand safety stock."""
    if service_level <= 0 or service_level >= 1:
        raise ValueError(f"service_level must be in (0, 1); got {service_level}")
    return float(norm.ppf(service_level))


def compute_reorder(sku_forecast, stock_snapshot, brands_config,
                    today=None):
    """Aggregate SKU × canal forecasts to SKU totals and compute reorder.

    Args:
        sku_forecast: DataFrame (cod_produs, sku, furnizor, canal, ds,
                      yhat, yhat_lo, yhat_hi, method). Output of hierarchy.
        stock_snapshot: DataFrame (cod_produs, stock_on_hand, stock_on_order,
                        snapshot_date). Only the newest snapshot per SKU is used.
        brands_config: DataFrame (furnizor, lead_time_weeks, moq_units,
                       target_service_level, review_period_weeks,
                       summer_restriction, financed_by_supplier).
        today: datetime.date (defaults to datetime.date.today()).

    Returns DataFrame with columns:
        cod_produs, sku, furnizor, stock_on_hand, demand_over_lead_time,
        safety_stock, reorder_point, suggested_qty, order_by_date,
        rationale, urgency.
    """
    if today is None:
        today = dt.date.today()
    today = pd.Timestamp(today)

    if sku_forecast.empty:
        return pd.DataFrame(columns=[
            "cod_produs", "sku", "furnizor", "stock_on_hand",
            "demand_over_lead_time", "safety_stock", "reorder_point",
            "suggested_qty", "order_by_date", "rationale", "urgency",
        ])

    fc = sku_forecast.copy()
    fc["ds"] = pd.to_datetime(fc["ds"])
    fc = fc.sort_values(["cod_produs", "ds"])

    # Collapse canals — reorder decisions are per-SKU, not per-canal.
    by_sku = (fc.groupby(["cod_produs", "sku", "furnizor", "ds"], as_index=False)
                .agg(yhat=("yhat", "sum")))

    # Latest snapshot per SKU
    if stock_snapshot is not None and not stock_snapshot.empty:
        snap = stock_snapshot.copy()
        snap["snapshot_date"] = pd.to_datetime(snap["snapshot_date"])
        snap = snap.sort_values("snapshot_date").groupby("cod_produs").tail(1)
        snap = snap[["cod_produs", "stock_on_hand", "stock_on_order",
                     "snapshot_date"]]
    else:
        snap = pd.DataFrame(columns=["cod_produs", "stock_on_hand",
                                     "stock_on_order", "snapshot_date"])

    cfg = brands_config.copy()
    cfg_idx = cfg.set_index("furnizor")

    rows = []
    for (cod, sku, furnizor), grp in by_sku.groupby(["cod_produs", "sku",
                                                      "furnizor"]):
        if furnizor not in cfg_idx.index:
            # Default if no config — conservative
            lead_w = 4
            review_w = 1
            sl = 0.95
            moq = None
            summer_restr = 0
        else:
            row = cfg_idx.loc[furnizor]
            lead_w = int(row["lead_time_weeks"])
            review_w = int(row["review_period_weeks"] or 1)
            sl = float(row["target_service_level"] or 0.95)
            moq = row.get("moq_units")
            if pd.isna(moq):
                moq = None
            summer_restr = int(row.get("summer_restriction") or 0)

        z = _z_score(sl)
        protection = lead_w + review_w

        grp = grp.sort_values("ds")
        future = grp[grp["ds"] >= today]
        if future.empty:
            # Forecast didn't cover today forward — skip.
            continue

        demand_lead = float(future["yhat"].head(lead_w).sum())
        demand_protect = float(future["yhat"].head(protection).sum())

        # Weekly demand std from the FULL forecast horizon (proxy for σ).
        sigma = float(future["yhat"].std(ddof=0) or 0)
        safety = z * sigma * (protection ** 0.5)

        reorder_pt = demand_lead + safety
        target = demand_protect + safety

        snap_row = snap[snap["cod_produs"] == cod]
        if snap_row.empty:
            on_hand = 0.0
            on_order = 0.0
            has_stock = False
        else:
            on_hand = float(snap_row["stock_on_hand"].iloc[0] or 0)
            on_order = float(snap_row["stock_on_order"].iloc[0] or 0)
            has_stock = True

        available = on_hand + on_order

        # Urgency
        if not has_stock:
            urgency = "unknown"
        elif available < safety:
            urgency = "critical"
        elif available < reorder_pt:
            urgency = "high"
        else:
            urgency = "normal"

        # Suggested qty
        if urgency in ("critical", "high"):
            raw_qty = max(0.0, target - available)
            if moq and moq > 0 and raw_qty > 0:
                # Round UP to next multiple of MOQ
                mult = -(-raw_qty // moq)  # ceil div
                suggested_qty = mult * moq
            else:
                suggested_qty = raw_qty
        else:
            suggested_qty = 0.0

        # Order-by date: days of coverage remaining above safety_stock.
        # Expressed as today + floor((available - safety) / weekly_demand) * 7.
        weekly_demand = demand_lead / max(1, lead_w)
        if weekly_demand > 0 and has_stock:
            coverage_weeks = max(0.0, (available - safety) / weekly_demand)
            order_by = today + pd.Timedelta(weeks=coverage_weeks)
        else:
            order_by = today

        # Rationale text (short, for UI)
        parts = [
            f"lead {lead_w}w",
            f"review {review_w}w",
            f"SL {int(sl*100)}%",
        ]
        if summer_restr:
            parts.append("summer-restricted")
        rationale = " · ".join(parts)

        rows.append({
            "cod_produs": cod,
            "sku": sku,
            "furnizor": furnizor,
            "stock_on_hand": on_hand if has_stock else None,
            "demand_over_lead_time": round(demand_lead, 2),
            "safety_stock": round(safety, 2),
            "reorder_point": round(reorder_pt, 2),
            "suggested_qty": round(suggested_qty, 0) if moq else round(suggested_qty, 2),
            "order_by_date": order_by.date().isoformat(),
            "rationale": rationale,
            "urgency": urgency,
        })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sqlite3
    from forecast.data import weekly_brand_channel, sku_mix_recent
    from forecast.models import (fit_and_forecast, compute_q4_multipliers,
                                 compute_summer_dampener, apply_overlays)
    from forecast.hierarchy import allocate_to_sku
    from forecast.schema import DB_PATH

    df = weekly_brand_channel("Basilur")
    q4 = compute_q4_multipliers(df)
    summer = compute_summer_dampener(df)
    fc = fit_and_forecast(df, horizon_weeks=24)
    static = df[["unique_id", "furnizor", "canal"]].drop_duplicates()
    brand_fc = apply_overlays(fc.merge(static, on="unique_id"), q4, summer)
    mix = sku_mix_recent("Basilur", weeks=12)
    sku_fc = allocate_to_sku(brand_fc, mix)

    with sqlite3.connect(DB_PATH) as conn:
        cfg = pd.read_sql_query("SELECT * FROM brands_config", conn)

    # Synthetic stock: nothing in DB yet
    stock = pd.DataFrame(columns=["cod_produs", "stock_on_hand",
                                  "stock_on_order", "snapshot_date"])
    ro = compute_reorder(sku_fc, stock, cfg)
    print(f"reorder rows: {len(ro)}")
    print(f"urgency mix: {ro['urgency'].value_counts().to_dict()}")
    print("\nTop 10 by demand_over_lead_time:")
    print(ro.nlargest(10, "demand_over_lead_time")[
        ["cod_produs", "sku", "demand_over_lead_time",
         "safety_stock", "reorder_point", "urgency"]
    ].to_string(index=False))
