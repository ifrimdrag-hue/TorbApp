import json
import sqlite3 as _sqlite3


def test_shopify_api_connection_test_unconfigured(client):
    """GET /api/stocuri/shopify/connection-test returns ok=False when not configured."""
    resp = client.get('/api/stocuri/shopify/connection-test')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert 'ok' in data


def _seed_session(db_path, filename='test.xlsx', sync_at='2026-06-05 14:32:00'):
    """Insert one session with two rows; return session_id."""
    with _sqlite3.connect(db_path) as c:
        cur = c.execute(
            "INSERT INTO shopify_sync_sessions (sync_at, filename) VALUES (?, ?)",
            (sync_at, filename),
        )
        session_id = cur.lastrowid
        c.executemany(
            """INSERT INTO shopify_sync_rows
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
