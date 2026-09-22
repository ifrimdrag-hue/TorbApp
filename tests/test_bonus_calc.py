"""Tests for the bonus calculation engine (app/bonus_calc.py).

All functions are pure (no DB dependency) so no fixture is needed.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from bonus_calc import (payout_multiplier, calc_kpi, calc_agent_month,
                        sales_gate_blocked, sales_realizare, SALES_GATE)


# ── payout_multiplier ─────────────────────────────────────────────────────────

def test_payout_below_gate_returns_zero():
    assert payout_multiplier(0.0) == 0.0
    assert payout_multiplier(0.79) == 0.0

def test_payout_at_80pct():
    assert payout_multiplier(0.80) == 0.5

def test_payout_at_90pct():
    assert payout_multiplier(0.89) == 0.5   # sub prag → treapta anterioară
    assert payout_multiplier(0.90) == 0.8
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


# ── payout_multiplier cu grilă parametrizabilă (Task 2) ──────────────────────

_GRID = [(0.0, 0.0), (0.80, 0.5), (0.90, 0.8), (1.00, 1.0),
         (1.02, 1.1), (1.10, 1.2), (1.20, 1.5)]

def test_payout_with_explicit_grid():
    assert payout_multiplier(0.79, _GRID) == 0.0
    assert payout_multiplier(0.80, _GRID) == 0.5
    assert payout_multiplier(1.50, _GRID) == 1.5

def test_payout_default_grid_backward_compat():
    assert payout_multiplier(0.80) == 0.5  # fără grid → folosește PAYOUT_GRID


# ── calc_kpi + calc_agent_month (Task 3) ─────────────────────────────────────

def test_calc_kpi_gated_below_80():
    r = calc_kpi({"tip": "vanzari", "target": 100.0, "actual": 79.0, "pondere": 0.5}, _GRID)
    assert r["realizare"] == 0.79
    assert r["multiplier"] == 0.0
    assert r["weighted"] == 0.0

def test_calc_kpi_at_target():
    r = calc_kpi({"tip": "vanzari", "target": 100.0, "actual": 100.0, "pondere": 0.5}, _GRID)
    assert r["realizare"] == 1.0
    assert r["multiplier"] == 1.0
    assert r["weighted"] == 0.5

def test_calc_kpi_zero_target_is_zero():
    r = calc_kpi({"tip": "incasari", "target": 0.0, "actual": 50.0, "pondere": 0.3}, _GRID)
    assert r["realizare"] == 0.0
    assert r["weighted"] == 0.0

def test_calc_agent_month_sums_weighted_bonus():
    kpis = [
        {"tip": "vanzari", "target": 100.0, "actual": 100.0, "pondere": 0.6},
        {"tip": "marja",   "target": 100.0, "actual": 120.0, "pondere": 0.4},
    ]
    out = calc_agent_month(4000.0, 0.0, kpis, _GRID)
    assert out["scor"] == 1.2
    assert out["total_bonus"] == 4800.0
    assert out["kpis"][0]["bonus"] == 2400.0
    assert out["kpis"][1]["bonus"] == 2400.0
    assert out["total_pondere"] == 1.0

def test_calc_agent_month_penalty():
    kpis = [{"tip": "vanzari", "target": 100.0, "actual": 100.0, "pondere": 1.0}]
    out = calc_agent_month(1000.0, 0.10, kpis, _GRID)
    assert out["total_bonus"] == 900.0


# ── Poarta pe vânzări (gate global) ──────────────────────────────────────────

def test_sales_realizare_none_without_target():
    assert sales_realizare([{"tip": "marja", "target": 100.0, "actual": 100.0}]) is None
    assert sales_realizare([{"tip": "vanzari", "target": 0.0, "actual": 50.0}]) is None

def test_sales_realizare_aggregates_rows():
    kpis = [{"tip": "vanzari", "target": 100.0, "actual": 40.0},
            {"tip": "vanzari", "target": 100.0, "actual": 100.0}]
    assert sales_realizare(kpis) == 0.7

def test_sales_gate_blocked_below_threshold():
    assert sales_gate_blocked([{"tip": "vanzari", "target": 100.0, "actual": 79.0}])
    assert not sales_gate_blocked([{"tip": "vanzari", "target": 100.0, "actual": 80.0}])
    # fără target de vânzări poarta nu se aplică
    assert not sales_gate_blocked([{"tip": "marja", "target": 100.0, "actual": 10.0}])

def test_gate_zeroes_every_kpi_even_when_achieved():
    kpis = [
        {"tip": "vanzari", "target": 100.0, "actual": 79.0, "pondere": 0.5},
        {"tip": "marja",   "target": 100.0, "actual": 150.0, "pondere": 0.3},
        {"tip": "brand",   "target": 100.0, "actual": 100.0, "pondere": 0.2},
    ]
    out = calc_agent_month(4000.0, 0.0, kpis, _GRID)
    assert out["gate_vanzari"] is True
    assert out["gate_prag"] == SALES_GATE
    assert out["scor"] == 0.0
    assert out["total_bonus"] == 0.0
    assert all(k["multiplier"] == 0.0 and k["bonus"] == 0.0 for k in out["kpis"])
    # realizarea rămâne vizibilă, doar plata e blocată
    assert out["kpis"][1]["realizare"] == 1.5
    assert all(k["blocat_gate"] for k in out["kpis"])

def test_gate_not_applied_at_exactly_80():
    kpis = [
        {"tip": "vanzari", "target": 100.0, "actual": 80.0, "pondere": 0.5},
        {"tip": "marja",   "target": 100.0, "actual": 100.0, "pondere": 0.5},
    ]
    out = calc_agent_month(1000.0, 0.0, kpis, _GRID)
    assert out["gate_vanzari"] is False
    assert out["scor"] == 0.75
    assert out["total_bonus"] == 750.0

def test_gate_ignored_when_no_sales_objective():
    kpis = [{"tip": "marja", "target": 100.0, "actual": 100.0, "pondere": 1.0}]
    out = calc_agent_month(1000.0, 0.0, kpis, _GRID)
    assert out["gate_vanzari"] is False
    assert out["total_bonus"] == 1000.0
