"""Exports for the list/report pages: context, filters, period, Excel, PPT, authz."""

import pytest

AN = 2026
EMPTY_MONTH = 2  # the seed only has month 1, so month 2 yields no rows

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PPT_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'


def _rows(sheet):
    """Sheets are either a plain row list or {'rows', 'headers'} (basilur)."""
    return sheet['rows'] if isinstance(sheet, dict) else sheet


def test_team_context_shape(flask_app):
    """Structure only — the session DB is shared and several other test modules
    insert transactions, so figures are asserted against a monkeypatched query
    in test_team_cards_render_the_period_totals instead."""
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('team', AN, None, {})
    assert ctx['nav'] == 'team'
    assert ctx['filename_base'] == f'echipa_{AN}'
    assert list(ctx['sheets']) == [f'Echipa {AN}', f'Echipa {AN - 1}']
    assert 'Agent Test' in [r['agent'] for r in ctx['sheets'][f'Echipa {AN}']]
    assert len(ctx['cards']) == 4
    assert all(isinstance(v, str) for _, v in ctx['cards'])


def test_team_cards_render_the_period_totals(flask_app, monkeypatch):
    import queries
    from exports import overviews
    monkeypatch.setattr(queries, 'team_table', lambda an, **kw: [
        {'agent': 'A', 'val_neta': 500, 'marja_bruta': 200, 'marja_neta': 200},
        {'agent': 'B', 'val_neta': 400, 'marja_bruta': 150, 'marja_neta': 150},
    ])
    with flask_app.app_context():
        ctx = overviews.build_context('team', AN, None, {})
    # 900 net, 350 margin -> 38.9%.
    assert ctx['cards'] == [
        ("Val. Netă", "900 RON"),
        ("Marjă Brută", "350 RON / 38.9%"),
        ("Marjă Netă", "350 RON / 38.9%"),
        ("Nr. Agenți", "2"),
    ]


def test_clients_context_shape(flask_app):
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('clients', AN, None, {})
    assert ctx['nav'] == 'clients'
    assert ctx['filename_base'] == f'clienti_{AN}'
    assert list(ctx['sheets']) == [f'Clienți {AN}']
    codes = [r['cod_client'] for r in _rows(ctx['sheets'][f'Clienți {AN}'])]
    assert 'C001' in codes and 'KAUFLAND' in codes


def test_clients_context_honours_brand_filter(flask_app):
    from exports import overviews
    with flask_app.app_context():
        ctx = overviews.build_context('clients', AN, None, {'brand': 'Basilur'})
    codes = [r['cod_client'] for r in _rows(ctx['sheets'][f'Clienți {AN}'])]
    assert codes == ['C001']


@pytest.mark.parametrize('report', ['team', 'clients'])
def test_context_honours_luna(flask_app, report):
    """Month 2 has no seeded rows, so its period sheet must come back empty
    while the unfiltered context has data. /export/team used to drop luna."""
    from exports import overviews
    with flask_app.app_context():
        full = overviews.build_context(report, AN, None, {})
        empty = overviews.build_context(report, AN, EMPTY_MONTH, {})
    first = list(full['sheets'])[0]
    assert _rows(full['sheets'][first])
    assert not _rows(empty['sheets'][first])
    assert empty['subtitle'] == '2026 · Februarie'


@pytest.mark.parametrize('report', ['team', 'clients'])
@pytest.mark.parametrize('luna', [13, -1])
def test_context_rejects_out_of_range_luna(flask_app, report, luna):
    from exports import overviews
    with flask_app.app_context():
        assert overviews.build_context(report, AN, luna, {}) is None


def test_context_unknown_report_returns_none(flask_app):
    from exports import overviews
    with flask_app.app_context():
        assert overviews.build_context('nope', AN, None, {}) is None


@pytest.mark.parametrize('report', ['team', 'clients'])
def test_context_luna_zero_is_year_to_date(flask_app, report):
    from exports import overviews
    with flask_app.app_context():
        zero = overviews.build_context(report, AN, 0, {})
        none = overviews.build_context(report, AN, None, {})
    assert zero['subtitle'] == none['subtitle']
    for name in none['sheets']:
        assert len(_rows(zero['sheets'][name])) == len(_rows(none['sheets'][name]))


def test_excel_sheet_is_not_truncated_to_the_deck_limit(flask_app, monkeypatch):
    """The deck caps at 15 rows and says so in its caption; the workbook must
    still carry every row."""
    import queries
    from exports import overviews
    fake = [{'client': f'Client {i}', 'cod_client': f'K{i}', 'agent': 'A',
             'tip_client': 'X', 'judet_client': 'Y', 'val_neta': 100 - i,
             'marja_bruta': 10, 'marja_bruta_pct': 10.0, 'marja_neta': 10,
             'marja_neta_pct': 10.0, 'ultima_comanda': '2026-01-15',
             'zile_inactiv': 1, 'nr_branduri': 1, 'delta_vn': None}
            for i in range(40)]
    monkeypatch.setattr(queries, 'clients_list', lambda *a, **k: fake)
    with flask_app.app_context():
        ctx = overviews.build_context('clients', AN, None, {})
    assert len(_rows(ctx['sheets'][f'Clienți {AN}'])) == 40
    assert len(ctx['tables'][0]['rows']) == 15
    assert ctx['tables'][0]['title'] == f'Clienți {AN} — top 15 din 40'
