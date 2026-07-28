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
    expected = round((kpi['marja_neta'] or 0) * 100 / (kpi['val_neta'] or 1), 1)
    assert kpi['marja_neta_pct'] == pytest.approx(expected, abs=0.1)


def test_agent_kpi_marja_neta_pct_is_zero_without_sales(flask_app):
    import queries
    with flask_app.app_context():
        kpi = queries.agent_kpi('Agent Inexistent', AN)
    assert kpi['marja_neta_pct'] == 0
