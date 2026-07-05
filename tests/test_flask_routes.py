"""Flask route smoke tests using the test client.

Verifies every main page returns HTTP 200 with an empty (schema-only) DB.
Also checks key API endpoints return valid JSON.
"""
import json


MAIN_ROUTES = [
    '/',
    '/clients',
    '/team',
    '/products',
    '/profitabilitate',
    '/bonus',
    '/conditii',
    '/preturi',
    '/forecast',
    '/forecast/setari',
    '/actualizare',
]

API_JSON_ROUTES = [
    '/api/actualizare-date/status',
    '/api/clienti-export',
]


def test_main_routes_return_200(client):
    for path in MAIN_ROUTES:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"


def test_api_json_routes_return_200_and_valid_json(client):
    for path in API_JSON_ROUTES:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"
        data = json.loads(resp.data)
        assert data is not None


def test_404_returns_custom_page(client):
    resp = client.get('/nonexistent-route-xyz')
    assert resp.status_code == 404
    # App has a custom 404 — should still return HTML, not a bare Flask error
    assert b'404' in resp.data or b'<!DOCTYPE' in resp.data


def test_ask_page_loads(client):
    resp = client.get('/ask')
    assert resp.status_code == 200


def test_api_actualizare_status_fields(client):
    resp = client.get('/api/actualizare-date/status')
    data = json.loads(resp.data)
    assert 'status' in data


def test_comenzi_api_list_empty(client):
    # No orders in test DB → should return wrapped list, not 500
    resp = client.get('/api/comenzi/drafts')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    # API returns {"ok": true, "items": [...]}
    assert 'items' in data
    assert isinstance(data['items'], list)


def test_clienti_search_empty(client):
    resp = client.get('/api/clienti/search?q=test')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    # API returns {"ok": true, "items": [...]}
    assert 'items' in data
    assert isinstance(data['items'], list)


def test_forecast_setari_returns_brands(client):
    resp = client.get('/forecast/setari')
    assert resp.status_code == 200
    # Page should render even with empty termene_aprovizionare
    assert b'<!DOCTYPE' in resp.data or b'<html' in resp.data


def test_forecast_page_has_no_velocity_toggle(client):
    """The 3 ani / 90 zile toggle was retired — display uses the configured
    historical window (medie sezonieră)."""
    resp = client.get('/forecast?tab=stoc')
    assert resp.status_code == 200, resp.status_code
    assert b'velInput' not in resp.data
    assert 'medie sezonier'.encode('utf-8') in resp.data


def test_stocuri_shopify_history_elements_present(client):
    """The /stocuri page must contain Shopify history DOM elements so the history card renders."""
    resp = client.get('/stocuri')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'id="syncHistoryBody"' in html, "Shopify history tbody missing from stoc page"
    assert 'id="btnHistoryLoad"' in html, "Incarca date button missing from stoc page"
    assert 'id="shopHistoricalBanner"' in html, "Historical view banner missing from stoc page"


def test_comanda_avanseaza_endpoint_removed(client):
    """A3: dead /avanseaza endpoint was deleted — route no longer exists."""
    resp = client.post('/api/comenzi/1/avanseaza')
    assert resp.status_code == 404


def test_clienti_export_add_rejects_unknown_code(client):
    """A1: adding an export client with a code absent from tranzactii is rejected."""
    resp = client.post('/api/clienti-export', json={
        'cod_client': 'NOSUCHCODE', 'client': 'Ghost Client', 'tara': 'HU',
    })
    d = resp.get_json()
    assert resp.status_code == 400
    assert 'error' in d


def test_clienti_export_add_accepts_known_code(client):
    """A1: a code present in tranzactii (seeded 'C001') is accepted."""
    resp = client.post('/api/clienti-export', json={
        'cod_client': 'C001', 'client': 'Client Test', 'tara': 'HU',
    })
    d = resp.get_json()
    assert resp.status_code == 200
    assert d['ok'] is True
    # cleanup so other tests aren't affected
    client.delete('/api/clienti-export/C001')
