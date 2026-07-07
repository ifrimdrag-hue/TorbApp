import io


def test_pnl_routes_registered(flask_app):
    endpoints = {r.endpoint for r in flask_app.url_map.iter_rules()}
    assert {'pnl.pnl', 'pnl.import_page', 'pnl.api_scan', 'pnl.api_upload',
            'pnl.alarm_config', 'pnl.api_alarm_config_save', 'pnl.export_pnl'} <= endpoints


def test_pnl_upload_rejects_non_xls(client):
    rv = client.post('/pnl/api/upload',
                     data={'file': (io.BytesIO(b'x'), 'bad.txt')},
                     content_type='multipart/form-data')
    assert rv.status_code == 400


def test_pnl_page_renders(client):
    rv = client.get('/pnl')
    assert rv.status_code == 200
    assert b'CIFRA DE AFACERI NETA' in rv.data
    assert b'EBITDA' in rv.data


def test_pnl_import_page_renders(client):
    rv = client.get('/pnl/import')
    assert rv.status_code == 200
    assert b'Import balante' in rv.data


def test_pnl_alarm_config_page_renders(client):
    rv = client.get('/pnl/alarm-config')
    assert rv.status_code == 200
    assert b'Configurare alarme' in rv.data


def test_nav_has_pnl_link(client):
    rv = client.get('/pnl')
    assert b"url_for" not in rv.data  # rendered, not raw
    assert b'/pnl' in rv.data
