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
