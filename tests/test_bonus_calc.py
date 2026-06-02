"""Tests for the bonus calculation engine (app/bonus_calc.py).

All functions are pure (no DB dependency) so no fixture is needed.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from bonus_calc import payout_multiplier, calc_month, simulate


# ── payout_multiplier ─────────────────────────────────────────────────────────

def test_payout_below_gate_returns_zero():
    assert payout_multiplier(0.0) == 0.0
    assert payout_multiplier(0.79) == 0.0

def test_payout_at_80pct():
    assert payout_multiplier(0.80) == 0.5

def test_payout_at_95pct():
    assert payout_multiplier(0.95) == 0.8

def test_payout_at_100pct():
    assert payout_multiplier(1.00) == 1.0

def test_payout_at_102pct():
    assert payout_multiplier(1.02) == 1.1

def test_payout_at_110pct():
    assert payout_multiplier(1.10) == 1.2

def test_payout_at_120pct_and_above():
    assert payout_multiplier(1.20) == 1.5
    assert payout_multiplier(1.50) == 1.5


# ── calc_month ────────────────────────────────────────────────────────────────

_BASE_PARAMS = {
    "monthly_bonus": 4000,
    "w_sales": 0.45, "w_margin": 0.25, "w_strategic": 0.30,
    "gate_sales": 0.80, "gate_margin": 0.80,
    "penalty": 0.0, "growth_pct": 0.20,
}

def _month(base_s=100_000, actual_s=120_000,
           base_m=20_000, actual_m=24_000,
           strategic_att=1.0, coll=1.0):
    return {
        "base_sales": base_s, "actual_sales": actual_s,
        "base_margin": base_m, "actual_margin": actual_m,
        "strategic_att": strategic_att, "collection_factor": coll,
    }


def test_calc_month_full_achievement():
    result = calc_month(_BASE_PARAMS, _month())
    # sales att = 120k / (100k*1.2) = 1.0 → payout 1.0; margin same
    assert result["sales_att"] == 1.0
    assert result["margin_att"] == 1.0
    assert result["gate_sales_ok"] is True
    assert result["gate_margin_ok"] is True
    assert result["total_bonus"] > 0

def test_calc_month_sales_gate_fails():
    # actual_sales = 50k, target = 100k*1.2 = 120k → att 0.42 < 0.80 gate
    result = calc_month(_BASE_PARAMS, _month(actual_s=50_000))
    assert result["gate_sales_ok"] is False
    assert result["sales_bonus"] == 0.0
    assert result["strategic_bonus"] == 0.0  # strategic requires both gates

def test_calc_month_margin_gate_fails():
    result = calc_month(_BASE_PARAMS, _month(actual_m=10_000))
    assert result["gate_margin_ok"] is False
    assert result["margin_bonus"] == 0.0
    assert result["strategic_bonus"] == 0.0

def test_calc_month_penalty_reduces_bonus():
    params = {**_BASE_PARAMS, "penalty": 0.5}
    full = calc_month(_BASE_PARAMS, _month())
    penalized = calc_month(params, _month())
    assert penalized["total_bonus"] < full["total_bonus"]

def test_calc_month_collection_factor_scales_bonus():
    half = calc_month(_BASE_PARAMS, _month(coll=0.5))
    full = calc_month(_BASE_PARAMS, _month(coll=1.0))
    assert abs(half["total_bonus"] - full["total_bonus"] / 2) < 1.0

def test_calc_month_zero_base_returns_zero_bonus():
    result = calc_month(_BASE_PARAMS, _month(base_s=0, base_m=0))
    assert result["total_bonus"] == 0.0

def test_calc_month_overachievement_caps_at_1_5x():
    result = calc_month(_BASE_PARAMS, _month(actual_s=300_000, actual_m=60_000,
                                              strategic_att=1.5))
    assert result["sales_mult"] == 1.5
    assert result["margin_mult"] == 1.5
    assert result["strategic_mult"] == 1.5


# ── simulate ──────────────────────────────────────────────────────────────────

def test_simulate_annual_total():
    months_data = [_month() for _ in range(12)]
    result = simulate(_BASE_PARAMS, months_data)
    assert len(result["months"]) == 12
    assert result["annual_bonus"] == sum(m["total_bonus"] for m in result["months"])
    assert result["annual_target"] == 4000 * 12

def test_simulate_payout_pct():
    months_data = [_month() for _ in range(12)]
    result = simulate(_BASE_PARAMS, months_data)
    expected_pct = round(result["annual_bonus"] / result["annual_target"] * 100, 1)
    assert result["payout_pct"] == expected_pct

def test_simulate_month_labels():
    months_data = [_month() for _ in range(3)]
    result = simulate(_BASE_PARAMS, months_data)
    assert result["months"][0]["month_label"] == "Ian"
    assert result["months"][1]["month_label"] == "Feb"
    assert result["months"][2]["month_label"] == "Mar"
