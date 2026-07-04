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
