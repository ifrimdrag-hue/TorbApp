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
