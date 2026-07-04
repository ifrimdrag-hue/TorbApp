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


def test_article_profile_new_listing_uses_short_window(monkeypatch):
    today = date(2026, 7, 15)
    params = {"fereastra_luni": 36, "sezonalitate_min_luni": 24,
              "indice_sezonier_min": 0.2, "indice_sezonier_max": 5.0,
              "prag_delistare_zile": 180, "prag_delistare_mult": 3}
    # One RO client, first sale 4 closed months ago, 100/mo each of 4 months.
    rows = []
    for (y, m) in [(2026, 3), (2026, 4), (2026, 5), (2026, 6)]:
        rows.append({"cod_client": "C1", "client": "Client 1", "sku": "S",
                     "cod_produs": "100", "market": "ro",
                     "d": date(y, m, 10), "qty": 100.0})
    prof = pe.article_monthly_profiles("X", params, today=today, _rows=rows)
    # <24 mo history -> seasonal index 1.0; base = 400/4 = 100.
    assert round(prof["S"]["ro"][7], 1) == 100.0
    assert prof["S"]["n_active"] == 1


def test_delisting_delistat_after_confirm_window():
    # Single purchase ~560d ago: past prag(180)+confirm(90)=270 -> DELISTAT.
    today = date(2026, 7, 15)
    r = pe.delisting_status([date(2025, 1, 1)], today, min_days=180, mult=3,
                            confirm_days=90)
    assert r["status"] == "DELISTAT"


def test_delisting_suspect_within_confirm_window():
    # ~200d ago: past prag(180) but < prag+confirm(270) -> still SUSPECT.
    today = date(2026, 7, 15)
    r = pe.delisting_status([date(2025, 12, 27)], today, min_days=180, mult=3,
                            confirm_days=90)
    assert r["status"] == "SUSPECT"


def test_neutral_months_supply_gap():
    # 3 clients active Jan-Jun; all zero in April -> April neutral.
    win = [(2026, m) for m in range(1, 7)]
    cmq = {c: {(2026, m): 10.0 for m in range(1, 7) if m != 4}
           for c in ("A", "B", "C")}
    neutral = pe.neutral_months(cmq, win, threshold_pct=70)
    assert (2026, 4) in neutral
    assert (2026, 1) not in neutral


def test_neutral_months_single_client_ignored():
    # One client skipping a month is churn, not a supply gap -> never neutral.
    win = [(2026, m) for m in range(1, 7)]
    cmq = {"A": {(2026, m): 10.0 for m in range(1, 7) if m != 4}}
    assert pe.neutral_months(cmq, win, threshold_pct=70) == set()


def test_is_inactive_six_months_zero():
    # Last sale 2025-11; last 6 closed months all zero -> INACTIV.
    assert pe.is_inactive({(2025, 11): 100.0}, date(2026, 7, 15), months=6) is True


def test_is_inactive_recent_sale_active():
    assert pe.is_inactive({(2026, 5): 100.0}, date(2026, 7, 15), months=6) is False


def test_is_inactive_seasonal_protected():
    # Strongly seasonal (Nov peak >=3.0) is never auto-inactivated in extrasezon.
    s_idx = {m: (5.0 if m == 11 else 0.5) for m in range(1, 13)}
    assert pe.is_inactive({(2025, 11): 100.0}, date(2026, 7, 15), months=6,
                          seasonal_idx=s_idx) is False


def test_neutral_month_excluded_from_mean():
    # 2 clients, both zero in April -> April neutral, dropped from the mean:
    # 5 sales of 100 over 5 eligible months = 100/client, x2 = base 200.
    today = date(2026, 7, 15)
    params = {"fereastra_luni": 36, "sezonalitate_min_luni": 24,
              "indice_sezonier_min": 0.2, "indice_sezonier_max": 5.0,
              "prag_delistare_zile": 180, "prag_delistare_mult": 3,
              "prag_neutru_multi_client": 70, "taiere_inactiv_luni": 6}
    rows = []
    for c in ("A", "B"):
        for m in (1, 2, 3, 5, 6):   # April missing for both clients
            rows.append({"cod_client": c, "client": c, "sku": "S",
                         "cod_produs": "100", "market": "ro",
                         "d": date(2026, m, 10), "qty": 100.0})
    prof = pe.article_monthly_profiles("X", params, today=today, _rows=rows)
    assert round(prof["S"]["ro"][7], 1) == 200.0
    assert prof["S"]["inactive"] is False


def test_article_profile_excludes_suspect_client(monkeypatch):
    today = date(2026, 7, 15)
    params = {"fereastra_luni": 36, "sezonalitate_min_luni": 24,
              "indice_sezonier_min": 0.2, "indice_sezonier_max": 5.0,
              "prag_delistare_zile": 180, "prag_delistare_mult": 3}
    rows = []
    # Active client, monthly Jan-Jun 2026.
    for m in range(1, 7):
        rows.append({"cod_client": "A", "client": "Activ", "sku": "S",
                     "cod_produs": "100", "market": "ro",
                     "d": date(2026, m, 10), "qty": 50.0})
    # Suspect client, last buy 2025-01 (>>270d ago).
    rows.append({"cod_client": "B", "client": "Plecat", "sku": "S",
                 "cod_produs": "100", "market": "ro",
                 "d": date(2025, 1, 10), "qty": 999.0})
    prof = pe.article_monthly_profiles("X", params, today=today, _rows=rows)
    assert prof["S"]["n_suspect"] == 1
    # Suspect contributes 0 -> only client A's base counts.
    assert prof["S"]["ro"][7] > 0
    assert prof["S"]["suspects"][0]["cod_client"] == "B"
