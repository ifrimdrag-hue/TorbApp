# tests/test_forecast_engine.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from forecast_engine import ForecastEngine

engine = ForecastEngine()

def test_seasonality_index_flat():
    sales = {i: 100.0 for i in range(1, 13)}
    idx = engine.seasonality_index(sales, 6)
    assert abs(idx - 1.0) < 0.01

def test_seasonality_index_peak():
    sales = {i: 100.0 for i in range(1, 13)}
    sales[12] = 200.0  # Decembrie dublu
    idx = engine.seasonality_index(sales, 12)
    assert idx > 1.4

def test_coverage_demand_basic():
    # 10 buc/zi, 30 zile acoperire → ~300
    demand = engine.coverage_demand(daily_rate=10.0, lead_days=0, season_idx=1.0)
    assert 290 < demand < 310  # 30 zile safety

def test_coverage_demand_with_lead():
    demand = engine.coverage_demand(daily_rate=10.0, lead_days=30, season_idx=1.0)
    assert 590 < demand < 610  # 30 lead + 30 safety = 60 zile

def test_apply_yoy_trend_growth():
    rate = engine.apply_yoy_trend(current_avg=120.0, prev_avg=100.0)
    assert abs(rate - 1.2) < 0.01

def test_apply_yoy_trend_no_prev():
    rate = engine.apply_yoy_trend(current_avg=100.0, prev_avg=0.0)
    assert rate == 1.0

def test_urgency_ceai():
    assert engine.urgency(100.0, 'Ceai') == 'critic'
    assert engine.urgency(160.0, 'Ceai') == 'atentie'
    assert engine.urgency(220.0, 'Ceai') == 'ok'

def test_urgency_ciocolata():
    assert engine.urgency(50.0, 'Ciocolata') == 'critic'
    assert engine.urgency(70.0, 'Ciocolata') == 'atentie'
    assert engine.urgency(100.0, 'Ciocolata') == 'ok'

def test_urgency_none():
    assert engine.urgency(None, 'Ceai') == 'fara_miscare'
