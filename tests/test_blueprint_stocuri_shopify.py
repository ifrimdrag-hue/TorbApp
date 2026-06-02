def test_shopify_page_loads(client):
    resp = client.get('/stocuri/shopify')
    assert resp.status_code == 200
    assert b'<!DOCTYPE' in resp.data or b'<html' in resp.data
