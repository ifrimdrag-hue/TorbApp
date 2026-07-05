"""Render smoke tests for the forecast UI: SUSPECT badge, seasonality gating,
transparency popover, suspects modal.

Asserts HTTP 200 (no template exception) across the tab combinations — the
test DB is schema-only, so this mainly guards against Jinja errors from
unguarded field access (r.n_suspect, r.sug_piete, ...).
"""

FORECAST_ROUTES = [
    '/forecast',
    '/forecast?tab=suggest',
    '/forecast?tab=stoc',
    '/forecast/setari',
]


def test_forecast_routes_render_200(client):
    for path in FORECAST_ROUTES:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"


def test_forecast_page_has_suspects_modal(client):
    """The omitted-clients modal + handlers ship with the page (items #1/#4)."""
    html = client.get('/forecast?tab=stoc').data.decode('utf-8')
    assert 'id="modalSuspects"' in html
    assert 'function openSuspects(' in html
    assert 'function openSuspectsIdx(' in html


def test_setari_page_params_and_typeahead(client):
    """/forecast/setari: all tunable params editable + client typeahead (items #5/#6)."""
    html = client.get('/forecast/setari').data.decode('utf-8')
    for cheie in ('fereastra_luni', 'sezonalitate_min_luni', 'confirmare_delistare_zile',
                  'taiere_inactiv_luni', 'prag_neutru_multi_client'):
        assert f'data-cheie="{cheie}"' in html, f"param {cheie} missing from setari"
    assert 'id="clientSearch"' in html
    assert 'id="clientSuggest"' in html
    assert '/api/clienti/search' in html


def test_testare_page_and_flag_gate(client):
    import feature_flags
    # Flag ON: page renders, sidebar shows the Testare link.
    feature_flags.SHOW_TESTING = True
    resp = client.get('/testare')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Checklist de testare' in html
    assert 'href="/decizii"' in html   # links to the decision doc
    assert 'data-label="Testare"' in client.get('/').data.decode('utf-8')
    # Decision doc is served from templates and gated by the same flag.
    dec = client.get('/decizii')
    assert dec.status_code == 200
    assert 'Decizii de validat' in dec.data.decode('utf-8')
    # Flag OFF: both routes 404 and the sidebar link is hidden.
    feature_flags.SHOW_TESTING = False
    try:
        assert client.get('/testare').status_code == 404
        assert client.get('/decizii').status_code == 404
        assert 'data-label="Testare"' not in client.get('/').data.decode('utf-8')
    finally:
        feature_flags.SHOW_TESTING = True


def test_forecast_page_has_no_model_toggle_or_compare(client):
    """After the flip the legacy model toggle + Comparație scaffolding is gone."""
    resp = client.get('/forecast?tab=stoc')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Model actual' not in html
    assert 'Comparație' not in html
    assert 'Sug. RO nou' not in html


def test_api_forecast_suggest_does_not_500(client):
    """Exercises the server path in api_forecast_suggest; the test DB lacks
    Basilur data so build_suggestion returns empty items gracefully — we're
    only checking the path doesn't raise."""
    resp = client.get('/api/forecast/suggest/Basilur')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
