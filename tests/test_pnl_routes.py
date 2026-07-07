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
