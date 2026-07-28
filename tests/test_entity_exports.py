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


# ── Context builders ─────────────────────────────────────────────────────────

ENTITY_IDENT = {
    'client': CLIENT,
    'agent': AGENT,
    'brand': BRAND,
    'produs': SKU,
}

ENTITY_NAV = {
    'client': 'clients',
    'agent': 'team',
    'brand': 'products',
    'produs': 'products',
}


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_build_context_shape(flask_app, entity):
    from exports import entities
    with flask_app.app_context():
        ctx = entities.build_context(entity, ENTITY_IDENT[entity], AN, None)
    assert ctx is not None
    assert ctx['nav'] == ENTITY_NAV[entity]
    assert ctx['title']
    assert ctx['filename_base']
    assert 1 <= len(ctx['cards']) <= 4
    assert all(isinstance(v, str) for _, v in ctx['cards'])
    assert len(ctx['sheets']) == 4
    for table in ctx['tables']:
        assert set(table) >= {'title', 'headers', 'rows', 'left', 'width'}


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_build_context_unknown_ident_returns_none(flask_app, entity):
    from exports import entities
    with flask_app.app_context():
        assert entities.build_context(entity, 'NU_EXISTA_XYZ', AN, None) is None


def test_build_context_unknown_entity_returns_none(flask_app):
    from exports import entities
    with flask_app.app_context():
        assert entities.build_context('nope', 'x', AN, None) is None


@pytest.mark.parametrize('entity', ['client', 'agent', 'brand', 'produs'])
def test_build_context_honours_luna(flask_app, entity):
    """Month 2 has no seeded rows, so its period sheets must come back empty
    while the unfiltered context has data."""
    from exports import entities
    with flask_app.app_context():
        full = entities.build_context(entity, ENTITY_IDENT[entity], AN, None)
        filtered = entities.build_context(entity, ENTITY_IDENT[entity], AN, EMPTY_MONTH)
    period_sheet = f'Clienți {AN}' if entity != 'client' else f'Produse {AN}'
    assert full['sheets'][period_sheet]
    assert filtered is None or not filtered['sheets'][period_sheet]


def test_period_label(flask_app):
    from exports import entities
    with flask_app.app_context():
        assert entities._period_label(2026, 7, None) == '2026 · Iulie'
        assert entities._period_label(2026, None, 7) == '2026 · Ian–Iul'
        assert entities._period_label(2026, None, 12) == '2026'
        assert entities._period_label(2026, None, None) == '2026'


def test_table_caption_reports_truncation(flask_app):
    from exports import entities
    rows = [{'x': i} for i in range(40)]
    table = entities._table('Clienți', 0.3, 6.9, rows, lambda r: {'X': str(r['x'])}, limit=15)
    assert table['title'] == 'Clienți — top 15 din 40'
    assert len(table['rows']) == 15
    assert table['headers'] == ['X']


def test_produs_context_aggregates_sku_variants(flask_app, monkeypatch):
    """sku_variants expansion must survive — the same article appears in
    tranzactii under several spellings and the page aggregates over all."""
    import queries
    from exports import entities
    seen = {}

    real_kpi = queries.product_kpi

    def spy(sku, an, **kw):
        seen['sku'] = sku
        return real_kpi(sku, an, **kw)

    monkeypatch.setattr(queries, 'product_kpi', spy)
    monkeypatch.setattr(queries, 'sku_variants', lambda s: [s, s + ' VARIANTA'])
    with flask_app.app_context():
        entities.build_context('produs', SKU, AN, None)
    assert seen['sku'] == [SKU, SKU + ' VARIANTA']
