"""Exports for the entity detail pages: context, Excel round-trip, PPT, authz."""

import pytest

AN = 2026
AGENT = 'Agent Test'
CLIENT = 'C001'
BRAND = 'Basilur'
SKU = 'SKU001'
EMPTY_MONTH = 2  # the seed only has month 1, so month 2 yields no rows


def test_agent_kpi_exposes_marja_neta_pct(flask_app):
    import queries
    with flask_app.app_context():
        kpi = queries.agent_kpi(AGENT, AN)
    assert 'marja_neta_pct' in kpi
    # Seed (tests/conftest.py): marja_bruta 200+150=350, val_neta 500+400=900,
    # no conditii_comerciale rows -> condition cost 0 -> marja_neta == marja_bruta.
    assert kpi['marja_neta'] == 350
    assert kpi['marja_neta_pct'] == pytest.approx(38.9, abs=0.1)


def test_agent_kpi_marja_neta_pct_is_zero_without_sales(flask_app):
    import queries
    with flask_app.app_context():
        kpi = queries.agent_kpi('Agent Inexistent', AN)
    assert kpi['marja_neta_pct'] == 0
