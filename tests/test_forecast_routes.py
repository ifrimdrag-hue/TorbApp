"""Render smoke tests for Task 10 forecast UI additions: model toggle,
SUSPECT badge, seasonality gating, transparency popover, compare view.

Asserts HTTP 200 (no template exception) across the model/compare/tab
combinations — the test DB is schema-only, so this mainly guards against
Jinja errors from unguarded field access (r.n_suspect, r.suggested_ro_nou, ...).
"""

FORECAST_ROUTES = [
    '/forecast',
    '/forecast?model=nou',
    '/forecast?model=nou&compare=1',
    '/forecast?tab=suggest',
    '/forecast/setari',
]


def test_forecast_routes_render_200(client):
    for path in FORECAST_ROUTES:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"


def test_forecast_compare_adds_delta_columns(client):
    resp = client.get('/forecast?tab=stoc&compare=1')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Sug. RO nou' in html
    assert 'Δ RO' in html


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


def test_forecast_default_page_has_no_compare_columns(client):
    resp = client.get('/forecast?tab=stoc')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Sug. RO nou' not in html


def test_forecast_model_toggle_present(client):
    resp = client.get('/forecast?tab=stoc')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Model actual' in html
    assert 'Model nou (client × articol)' in html


def test_forecast_compare_with_urgenta_filter_renders(client):
    """Compare with a narrow urgenta filter can leave rows without a nou
    counterpart (None) — the em-dash path must not raise a template error."""
    resp = client.get('/forecast?compare=1&urgenta=critic')
    assert resp.status_code == 200


def test_api_forecast_suggest_nou_does_not_500(client):
    """Exercises the nou server path in api_forecast_suggest; the test DB
    lacks Basilur data so build_suggestion returns empty items gracefully —
    we're only checking the nou branch doesn't raise."""
    resp = client.get('/api/forecast/suggest/Basilur?model=nou')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
