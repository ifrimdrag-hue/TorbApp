import json
from unittest.mock import AsyncMock, patch


def test_emag_preview_no_report_returns_200(client):
    """POST /api/stocuri/emag/preview with no file returns has_report=false."""
    class FakeResult:
        rows = []
        skus_not_in_emag = []
        warnings = []
        summary = {'total_emag_offers': 0, 'no_ean': 0}
        has_report = False

    with patch('blueprints.stocuri_emag.preview_emag_only', new=AsyncMock(return_value=FakeResult())):
        resp = client.post('/api/stocuri/emag/preview')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['has_report'] is False


def test_emag_preview_page_loads(client):
    resp = client.get('/stocuri/emag')
    assert resp.status_code == 200
    assert b'<!DOCTYPE' in resp.data or b'<html' in resp.data
