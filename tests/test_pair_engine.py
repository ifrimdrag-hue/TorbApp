from datetime import date
from forecast import pair_engine as pe


def test_window_clips_to_first_sale_not_36mo():
    # First sale 4 months ago -> window is 4 closed months, not 36.
    today = date(2026, 7, 15)
    first = date(2026, 3, 10)
    win = pe.build_window(first, today, window_months=36)
    assert win == [(2026, 3), (2026, 4), (2026, 5), (2026, 6)]


def test_window_capped_at_window_months():
    today = date(2026, 7, 15)
    first = date(2020, 1, 1)
    win = pe.build_window(first, today, window_months=36)
    assert len(win) == 36
    assert win[-1] == (2026, 6)   # last closed month
    assert win[0] == (2023, 7)


def test_mean_with_zeros_declines_toward_zero():
    # Sold 100 in one month, nothing since -> mean over 4 months = 25.
    window = [(2026, 3), (2026, 4), (2026, 5), (2026, 6)]
    pair = {(2026, 3): 100.0}
    assert pe.monthly_mean_with_zeros(pair, window) == 25.0


def test_mean_empty_window_is_zero():
    assert pe.monthly_mean_with_zeros({(2026, 3): 5}, []) == 0.0


def test_seasonality_flat_below_min_history():
    # 12 months of data < 24 -> no adjustment.
    qty = {(2025, m): 10.0 for m in range(1, 13)}
    idx = pe.seasonal_index(qty, min_history_months=24, cap_lo=0.2, cap_hi=5.0)
    assert set(idx.values()) == {1.0}


def test_seasonality_peaks_and_caps():
    # 36 months: Nov huge, rest ~1. Index for Nov must be capped at 5.0.
    qty = {}
    for y in (2023, 2024, 2025):
        for m in range(1, 13):
            qty[(y, m)] = 1.0
        qty[(y, 11)] = 1000.0
    idx = pe.seasonal_index(qty, min_history_months=24, cap_lo=0.2, cap_hi=5.0)
    assert idx[11] == 5.0
    assert 0.2 <= idx[1] <= 1.0


def test_delisting_monthly_client_stops_becomes_suspect():
    # Ordered monthly, last purchase 7 months ago -> SUSPECT (case #3).
    today = date(2026, 7, 15)
    dates = [date(2025, m, 1) for m in range(1, 13)]  # last = 2025-12-01
    r = pe.delisting_status(dates, today, min_days=180, mult=3)
    assert r["status"] == "SUSPECT"


def test_delisting_quarterly_client_stays_active():
    # Quarterly buyer, last purchase 5 months ago -> ACTIV (case #4).
    # Real calendar gaps (90, 91, 92, 137d) -> mean_interval=102.5,
    # prag = max(180, 3*102.5=307.5) = 307.5; 150d < 307.5.
    today = date(2026, 7, 15)
    dates = [date(2025, 1, 1), date(2025, 4, 1), date(2025, 7, 1),
             date(2025, 10, 1), date(2026, 2, 15)]
    r = pe.delisting_status(dates, today, min_days=180, mult=3)
    assert r["status"] == "ACTIV"
    assert r["prag"] == 307.5
