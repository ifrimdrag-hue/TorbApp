"""Client x article forecast core (spec §2, §4, §5).

Pure functions operate on in-memory month->qty dicts so they are unit
testable; article_monthly_profiles() adds the DB fetch + aggregation.
"""
from __future__ import annotations


def _month_add(y, m, delta):
    idx = (y * 12 + (m - 1)) + delta
    return idx // 12, idx % 12 + 1


def build_window(first_sale, today, window_months):
    """[start ... last closed month] as (year, month) tuples."""
    # Last closed month = month before the current (open) one.
    last_y, last_m = _month_add(today.year, today.month, -1)
    cap_y, cap_m = _month_add(today.year, today.month, -int(window_months))
    fs_y, fs_m = first_sale.year, first_sale.month
    # start = max(first_sale month, cap month)
    if (fs_y, fs_m) >= (cap_y, cap_m):
        start_y, start_m = fs_y, fs_m
    else:
        start_y, start_m = cap_y, cap_m
    if (start_y, start_m) > (last_y, last_m):
        return []
    out = []
    y, m = start_y, start_m
    while (y, m) <= (last_y, last_m):
        out.append((y, m))
        y, m = _month_add(y, m, 1)
    return out


def monthly_mean_with_zeros(pair_months, window):
    if not window:
        return 0.0
    total = sum(pair_months.get(ym, 0.0) for ym in window)
    return total / len(window)


def seasonal_index(article_month_qty, min_history_months, cap_lo, cap_hi):
    if len(article_month_qty) < min_history_months:
        return {m: 1.0 for m in range(1, 13)}
    by_month = {m: [] for m in range(1, 13)}
    for (_, m), q in article_month_qty.items():
        by_month[m].append(q)
    month_mean = {m: (sum(v) / len(v) if v else 0.0) for m, v in by_month.items()}
    overall = sum(month_mean.values()) / 12
    if overall <= 0:
        return {m: 1.0 for m in range(1, 13)}
    out = {}
    for m in range(1, 13):
        idx = month_mean[m] / overall
        out[m] = min(cap_hi, max(cap_lo, idx))
    return out


def delisting_status(purchase_dates, today, min_days, mult):
    if not purchase_dates:
        return {"status": "ACTIV", "days_since_last": None,
                "mean_interval": None, "prag": float(min_days)}
    ordered = sorted(purchase_dates)
    days_since_last = (today - ordered[-1]).days
    if len(ordered) >= 2:
        gaps = [(ordered[i] - ordered[i - 1]).days for i in range(1, len(ordered))]
        mean_interval = sum(gaps) / len(gaps)
        prag = max(float(min_days), mult * mean_interval)
    else:
        mean_interval = None
        prag = float(min_days)
    status = "SUSPECT" if days_since_last > prag else "ACTIV"
    return {"status": status, "days_since_last": days_since_last,
            "mean_interval": mean_interval, "prag": prag}
