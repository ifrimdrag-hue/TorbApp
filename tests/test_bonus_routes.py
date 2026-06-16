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
    with app.test_client() as c:
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


def test_build_agent_month_auto_actual(seed_bogdan):
    from queries.bonus import save_obiective
    from blueprints.bonus import build_agent_month
    save_obiective(2026, 6, 'Bogdan', 4000.0, 0.20,
                   [{"tip": "vanzari", "referinta": None, "target": 5000.0, "unitate": "ron", "pondere": 1.0}])
    out = build_agent_month('Bogdan', 'DRAGNEA BOGDAN', 2026, 6)
    assert out['kpis'][0]['actual'] == 5000.0
    assert out['kpis'][0]['realizare'] == 1.0
    assert out['total_bonus'] == 4000.0
