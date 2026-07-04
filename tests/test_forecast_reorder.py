from forecast import forecast_logic as fl


def test_round_up_to_bax():
    assert fl.round_up_to_bax(7, 12) == 12
    assert fl.round_up_to_bax(13, 12) == 24
    assert fl.round_up_to_bax(24, 12) == 24
    assert fl.round_up_to_bax(7.4, None) == 7


def test_case8_stock_covers_no_order():
    # Forecast 100/mo, lead 1 mo, coverage 1 mo, safety 0.25*100=25.
    # necesar = 100*2 + 25 = 225; available 500+200=700 -> suggestion 0.
    monthly = {m: 100.0 for m in range(1, 13)}
    r = fl.split_with_safety(
        monthly_ro=monthly, monthly_export={m: 0 for m in range(1, 13)},
        lead_days=30, available=700, base_ro=100.0, base_export=0.0,
        coef=0.25, coverage_days=30, buc_cutie=1)
    assert r["suggested_ro"] == 0


def test_safety_adds_to_demand():
    monthly = {m: 100.0 for m in range(1, 13)}
    r = fl.split_with_safety(
        monthly_ro=monthly, monthly_export={m: 0 for m in range(1, 13)},
        lead_days=30, available=0, base_ro=100.0, base_export=0.0,
        coef=0.25, coverage_days=30, buc_cutie=1)
    # ~ two months demand (200) + safety 25 = ~225, rounded.
    assert 220 <= r["suggested_ro"] <= 232


def test_build_suggestion_accepts_model_param(monkeypatch):
    from forecast import forecast_logic as fl

    def fake_profiles(furnizor, params, today=None, _rows=None):
        prof = {m: 10.0 for m in range(1, 13)}
        return {"SKU-Z": {"ro": prof, "export": {m: 0 for m in range(1, 13)},
                          "total": prof, "cod_produs": "100",
                          "suspects": [], "n_active": 1, "n_suspect": 0}}

    monkeypatch.setattr("forecast.pair_engine.article_monthly_profiles",
                        fake_profiles)
    monkeypatch.setattr(fl, "get_in_transit", lambda f: {})
    monkeypatch.setattr(fl, "_listing_changes", lambda f: {})
    monkeypatch.setattr(fl, "get_lead_time",
                        lambda f: {"zile_livrare": 30, "sezon_craciun": 0})
    monkeypatch.setattr(fl, "query", lambda *a, **k: [])
    monkeypatch.setattr(fl, "query_one", lambda *a, **k: {"d": None})
    res = fl.build_suggestion("AnyBrand", min_velocity=0, only_needed=False,
                              model="nou")
    assert res["items"][0]["n_suspect"] == 0
