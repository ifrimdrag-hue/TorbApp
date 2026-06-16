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


def test_build_agent_month_auto_actual(seed_bogdan):
    from queries.bonus import save_obiective
    from blueprints.bonus import build_agent_month
    save_obiective(2026, 6, 'Bogdan', 4000.0, 0.20,
                   [{"tip": "vanzari", "referinta": None, "target": 5000.0, "unitate": "ron", "pondere": 1.0}])
    out = build_agent_month('Bogdan', 'DRAGNEA BOGDAN', 2026, 6)
    assert out['kpis'][0]['actual'] == 5000.0
    assert out['kpis'][0]['realizare'] == 1.0
    assert out['total_bonus'] == 4000.0
