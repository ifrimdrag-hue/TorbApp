import json
import sqlite3 as _sqlite3


def test_shopify_api_connection_test_unconfigured(client):
    """GET /api/stocuri/shopify/connection-test returns ok=False when not configured."""
    resp = client.get('/api/stocuri/shopify/connection-test')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert 'ok' in data


def _seed_session(db_path, filename='test.xlsx', sync_at='2026-06-05 14:32:00',
                  user_id=None):
    """Insert one session with two rows; return session_id."""
    with _sqlite3.connect(db_path) as c:
        cur = c.execute(
            "INSERT INTO sync_sessions (sync_at, filename, user_id)"
            " VALUES (?, ?, ?)",
            (sync_at, filename, user_id),
        )
        session_id = cur.lastrowid
        c.executemany(
            """INSERT INTO sync_rows
               (session_id, inventory_item_id, sku, name, old_stock, new_stock, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (session_id, 'IID001', 'SKU001', 'Produs A', 10, 20, 'updated'),
                (session_id, 'IID002', 'SKU002', 'Produs B', 5, 0, 'updated'),
            ],
        )
    return session_id


def test_sync_history_returns_list(client):
    resp = client.get('/api/stocuri/shopify/sync-history')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)


def test_sync_history_returns_seeded_session(client, db_path):
    session_id = _seed_session(db_path, filename='raport_stoc.xlsx')
    resp = client.get('/api/stocuri/shopify/sync-history')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    session = next((s for s in data if s['id'] == session_id), None)
    assert session is not None
    assert session['filename'] == 'raport_stoc.xlsx'
    assert '-' in session['sync_at']   # formatted as dd-mm-yyyy HH:MM


def test_sync_history_max_ten(client, db_path):
    for i in range(12):
        _seed_session(db_path, filename=f'batch_{i}.xlsx')
    resp = client.get('/api/stocuri/shopify/sync-history')
    data = json.loads(resp.data)
    assert len(data) == 10


def test_sync_history_rows_for_session(client, db_path):
    session_id = _seed_session(db_path, filename='rows_test.xlsx')
    resp = client.get(f'/api/stocuri/shopify/sync-history/{session_id}')
    assert resp.status_code == 200
    rows = json.loads(resp.data)
    assert len(rows) == 2
    skus = {r['sku'] for r in rows}
    assert skus == {'SKU001', 'SKU002'}
    assert rows[0]['status'] == 'updated'


def test_sync_history_rows_unknown_session(client):
    resp = client.get('/api/stocuri/shopify/sync-history/99999')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data == []


def test_sync_saves_history_to_db(client, db_path, testadmin_id):
    from unittest.mock import patch, AsyncMock

    fake_result = type('R', (), {
        'results': [
            {'ok': True,  'inventory_item_id': 'IID_HIST_A',
             'sku': 'SKU_A', 'name': 'Produs A', 'error': None},
            {'ok': False, 'inventory_item_id': 'IID_HIST_B',
             'sku': 'SKU_B', 'name': 'Produs B', 'error': 'timeout'},
        ],
        'success_count': 1,
        'error_count': 1,
    })()

    payload = {
        'report_filename': 'stoc_test.xlsx',
        'rows_to_update': [
            {'inventory_item_id': 'IID_HIST_A', 'sku': 'SKU_A',
             'name': 'Produs A', 'old_stock': 5, 'new_stock': 10},
            {'inventory_item_id': 'IID_HIST_B', 'sku': 'SKU_B',
             'name': 'Produs B', 'old_stock': 3, 'new_stock': 0},
        ],
    }

    with patch('blueprints.stocuri_shopify.sync', new=AsyncMock(return_value=fake_result)):
        resp = client.post(
            '/api/stocuri/shopify/sync',
            data=json.dumps(payload),
            content_type='application/json',
        )

    assert resp.status_code == 200

    with _sqlite3.connect(db_path) as c:
        c.row_factory = _sqlite3.Row
        session = c.execute(
            "SELECT * FROM sync_sessions WHERE filename='stoc_test.xlsx'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert session is not None

        rows = c.execute(
            "SELECT * FROM sync_rows WHERE session_id=?", (session['id'],)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]['inventory_item_id'] == 'IID_HIST_A'
        assert rows[0]['old_stock'] == 5
        assert rows[0]['new_stock'] == 10
        assert rows[0]['status'] == 'updated'
        assert session['user_id'] == testadmin_id


def test_sync_history_returns_username(client, db_path, testadmin_id):
    session_id = _seed_session(db_path, filename='cu_user.xlsx', user_id=testadmin_id)
    resp = client.get('/api/stocuri/shopify/sync-history')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    session = next((s for s in data if s['id'] == session_id), None)
    assert session is not None
    assert session['username'] == 'testadmin'


def test_sync_history_username_empty_when_no_user(client, db_path):
    session_id = _seed_session(db_path, filename='fara_user.xlsx')
    resp = client.get('/api/stocuri/shopify/sync-history')
    data = json.loads(resp.data)
    session = next((s for s in data if s['id'] == session_id), None)
    assert session is not None
    assert session['username'] == ''
