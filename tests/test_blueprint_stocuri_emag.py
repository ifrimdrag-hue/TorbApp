import json
import sqlite3 as _sqlite3
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


def test_stoc_page_loads(client):
    resp = client.get('/stocuri')
    assert resp.status_code == 200
    assert b'<!DOCTYPE' in resp.data or b'<html' in resp.data


def test_stoc_emag_redirect(client):
    resp = client.get('/stocuri/emag')
    assert resp.status_code == 302
    assert '/stocuri' in resp.headers['Location']


def test_stoc_shopify_redirect(client):
    resp = client.get('/stocuri/shopify')
    assert resp.status_code == 302
    assert '/stocuri' in resp.headers['Location']


def _seed_emag_session(db_path, filename='raport_emag.xlsx',
                       sync_at='2026-06-09 10:15:00', user_id=None):
    """Insert one eMAG session with two rows; return session_id."""
    with _sqlite3.connect(db_path) as c:
        cur = c.execute(
            "INSERT INTO sync_sessions (sync_at, filename, platform, user_id)"
            " VALUES (?, ?, 'emag', ?)",
            (sync_at, filename, user_id),
        )
        session_id = cur.lastrowid
        c.executemany(
            """INSERT INTO sync_rows
               (session_id, inventory_item_id, sku, name, old_stock, new_stock, status, platform)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'emag')""",
            [
                (session_id, '1001', 'EAN001', 'Produs A', 10, 20, 'updated'),
                (session_id, '1002', 'EAN002', 'Produs B', 5, 0, 'updated'),
            ],
        )
    return session_id


def test_emag_sync_history_returns_username(client, db_path, testadmin_id):
    session_id = _seed_emag_session(db_path, filename='cu_user_emag.xlsx',
                                    user_id=testadmin_id)
    resp = client.get('/api/stocuri/emag/sync-history')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    session = next((s for s in data if s['id'] == session_id), None)
    assert session is not None
    assert session['username'] == 'testadmin'
    assert session['filename'] == 'cu_user_emag.xlsx'


def test_emag_sync_history_username_empty_when_no_user(client, db_path):
    session_id = _seed_emag_session(db_path, filename='fara_user_emag.xlsx')
    resp = client.get('/api/stocuri/emag/sync-history')
    data = json.loads(resp.data)
    session = next((s for s in data if s['id'] == session_id), None)
    assert session is not None
    assert session['username'] == ''


def test_emag_sync_history_rows_for_session(client, db_path):
    session_id = _seed_emag_session(db_path)
    resp = client.get(f'/api/stocuri/emag/sync-history/{session_id}')
    assert resp.status_code == 200
    rows = json.loads(resp.data)
    assert len(rows) == 2
    assert {r['ean'] for r in rows} == {'EAN001', 'EAN002'}


def test_emag_sync_saves_user_to_db(client, db_path, testadmin_id):
    fake_result = type('R', (), {
        'results': [{'ok': True, 'offer_id': 9001}],
        'success_count': 1,
        'error_count': 0,
    })()

    payload = {
        'report_filename': 'stoc_emag_test.xlsx',
        'rows_to_update': [
            {'offer_id': 9001, 'ean': 'EAN9001', 'name': 'Produs eMAG',
             'old_stock': 4, 'new_stock': 7},
        ],
    }

    with patch('blueprints.stocuri_emag.sync', new=AsyncMock(return_value=fake_result)):
        resp = client.post(
            '/api/stocuri/emag/sync',
            data=json.dumps(payload),
            content_type='application/json',
        )

    assert resp.status_code == 200

    with _sqlite3.connect(db_path) as c:
        c.row_factory = _sqlite3.Row
        session = c.execute(
            "SELECT * FROM sync_sessions WHERE filename='stoc_emag_test.xlsx'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert session is not None
        assert session['platform'] == 'emag'
        assert session['user_id'] == testadmin_id
