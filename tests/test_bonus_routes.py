import sys
import os
import sqlite3
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
import paths


@pytest.fixture
def app_client():
    from app import app
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        rv = c.post('/auth/login', data={'username': 'testadmin', 'password': 'testpass'})
        assert rv.status_code == 302  # login reușit → redirect
        yield c


@pytest.fixture
def seed_bogdan():
    conn = sqlite3.connect(paths.DB_PATH)
    conn.executemany(
        "INSERT INTO tranzactii (an, luna, data_dl, agent, furnizor, client, "
        "cod_client, val_neta, marja_bruta) VALUES (?,?,?,?,?,?,?,?,?)",
        [(2026, 6, '2026-06-10', 'DRAGNEA BOGDAN', 'Basilur', 'Cl', 'C1', 5000.0, 1500.0)])
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(paths.DB_PATH)
    conn.execute("DELETE FROM tranzactii WHERE cod_client='C1'")
    conn.execute("DELETE FROM bonus_lunar_config WHERE agent_key='Bogdan' AND an=2026 AND luna=6")
    conn.execute("DELETE FROM bonus_obiective_strategice WHERE agent_key='Bogdan' AND an=2026 AND luna=6")
    conn.commit()
    conn.close()


def test_obiective_page_renders(app_client):
    resp = app_client.get('/bonus/obiective?an=2026&luna=7')
    assert resp.status_code == 200
    assert b'Bogdan' in resp.data


def test_obiective_save_roundtrip(app_client):
    payload = {
        "an": 2026, "luna": 9, "agent_key": "Ionut",
        "monthly_bonus": 2000, "growth_pct": 0.20,
        "kpis": [{"tip": "vanzari", "referinta": None, "target": 50000,
                  "unitate": "ron", "pondere": 1.0}],
    }
    resp = app_client.post('/bonus/obiective/save', json=payload)
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    from queries.bonus import obiective
    assert len(obiective(2026, 9, 'Ionut')) == 1


def test_clienti_noi_gama_page(app_client, seed_bogdan):
    resp = app_client.get('/bonus/clienti-noi-gama?agent=DRAGNEA BOGDAN&gama=Basilur&an=2026&luna=6')
    assert resp.status_code == 200


def test_build_agent_month_auto_actual(seed_bogdan):
    from queries.bonus import save_obiective
    from blueprints.bonus import build_agent_month
    save_obiective(2026, 6, 'Bogdan', 4000.0, 0.20,
                   [{"tip": "vanzari", "referinta": None, "target": 5000.0, "unitate": "ron", "pondere": 1.0}])
    out = build_agent_month('Bogdan', 'DRAGNEA BOGDAN', 2026, 6)
    assert out['kpis'][0]['actual'] == 5000.0
    assert out['kpis'][0]['realizare'] == 1.0
    assert out['total_bonus'] == 4000.0


def test_inchidere_page_renders(app_client):
    resp = app_client.get('/bonus/inchidere?an=2026&luna=6')
    assert resp.status_code == 200


def test_inchidere_lock_freezes(app_client, seed_bogdan):
    import json
    from queries.bonus import save_obiective, obiective, istoric_get
    save_obiective(2026, 6, 'Bogdan', 4000.0, 0.20,
                   [{"tip": "incasari", "referinta": None, "target": 1000.0, "unitate": "ron", "pondere": 1.0}])
    kpi_id = obiective(2026, 6, 'Bogdan')[0]['id']
    payload = {"an": 2026, "luna": 6, "agent_key": "Bogdan", "penalty": 0.0,
               "grad_incasare": 1.0, "note": "ok",
               "manual": {str(kpi_id): 1000.0}}  # cheiat pe id, nu pe tip
    resp = app_client.post('/bonus/inchidere/lock', json=payload)
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    rec = istoric_get(2026, 6, 'Bogdan')
    assert rec['stare'] == 'inchis'
    # snapshot înghețat: încasări 1000/1000 → realizare 1.0 → bonus integral
    snap = json.loads(rec['lunar_data'])
    assert snap['kpis'][0]['actual'] == 1000.0
    assert snap['total_bonus'] == 4000.0
    # re-lock pe o lună deja închisă → respins cu 409
    resp2 = app_client.post('/bonus/inchidere/lock', json=payload)
    assert resp2.status_code == 409
