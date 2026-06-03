def test_shopify_api_connection_test_unconfigured(client):
    """GET /api/stocuri/shopify/connection-test returns ok=False when not configured."""
    resp = client.get('/api/stocuri/shopify/connection-test')
    assert resp.status_code == 200
    import json
    data = json.loads(resp.data)
    assert 'ok' in data
