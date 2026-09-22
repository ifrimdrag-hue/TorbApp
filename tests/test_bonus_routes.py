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
    conn.execute("DELETE FROM bonus_istoric WHERE agent_key='Bogdan' AND an=2026 AND luna=6")
    conn.commit()
    conn.close()


def test_obiective_page_renders(app_client):
    resp = app_client.get('/bonus/obiective?an=2026&luna=7')
    assert resp.status_code == 200
    assert b'Bogdan' in resp.data
    html = resp.get_data(as_text=True)
    assert 'bonus-cell' in html              # coloana "Bonus la țintă"
    assert 'data-py=' in html                # baseline pt. recalc target din creștere
    assert 'Reguli de comisionare' in html   # legenda grilă + prag 80%


def _grid_legend_fragments():
    """Fragments the legend must contain, derived from the DB grid itself."""
    from queries.bonus import payout_grid
    pos = [(t, m) for t, m in payout_grid('_default') if m > 0]
    return pos, ['%g%%' % (t * 100) for t, _ in pos] + ['%g&times;' % m for _, m in pos]


@pytest.mark.parametrize('url', ['/bonus?an=2026&luna=6', '/bonus/obiective?an=2026&luna=7'])
def test_payout_legend_matches_db_grid(app_client, url):
    pos, fragments = _grid_legend_fragments()
    html = app_client.get(url).get_data(as_text=True)
    for frag in fragments:
        assert frag in html, f'legenda grilei nu conține {frag} ({url})'
    assert '&lt;%g%% &rarr; 0 lei' % (pos[0][0] * 100) in html


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


def test_config_page_renders(app_client):
    resp = app_client.get('/bonus/config')
    assert resp.status_code == 200
    assert b'Bogdan' in resp.data


def test_config_add_agent(app_client):
    resp = app_client.post('/bonus/config/agent',
                           json={"agent_key": "TestX", "db_agent": "TEST X", "tip_agent": "field"})
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    from queries.bonus import bonus_agents
    assert 'TestX' in {a['agent_key'] for a in bonus_agents(activ_only=False)}


def test_config_add_agent_rejects_unsafe_key(app_client):
    resp = app_client.post('/bonus/config/agent',
                           json={"agent_key": "O'Brien'); alert(1)", "db_agent": "X"})
    assert resp.status_code == 400 and resp.get_json()['ok'] is False
    from queries.bonus import bonus_agents
    assert "O'Brien'); alert(1)" not in {a['agent_key'] for a in bonus_agents(activ_only=False)}


def test_obiective_save_blocked_when_month_closed(app_client, seed_bogdan):
    from queries.bonus import save_obiective, istoric_lock
    save_obiective(2026, 6, 'Bogdan', 4000.0, 0.20,
                   [{"tip": "vanzari", "referinta": None, "target": 5000.0, "unitate": "ron", "pondere": 1.0}])
    istoric_lock(2026, 6, 'Bogdan', '{}', 0.0, 1.0, 'test')
    resp = app_client.post('/bonus/obiective/save', json={
        "an": 2026, "luna": 6, "agent_key": "Bogdan", "monthly_bonus": 9999,
        "growth_pct": 0.20, "kpis": []})
    assert resp.status_code == 409


def test_bonus_export_ok(app_client):
    resp = app_client.get('/bonus/export?an=2026&luna=6')
    assert resp.status_code == 200
    assert 'spreadsheet' in resp.headers.get('Content-Type', '')


def test_bonus_tracker_renders(app_client, seed_bogdan):
    from queries.bonus import save_obiective
    save_obiective(2026, 6, 'Bogdan', 4000.0, 0.20,
                   [{"tip": "vanzari", "referinta": None, "target": 5000.0, "unitate": "ron", "pondere": 1.0}])
    resp = app_client.get('/bonus?an=2026&luna=6')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Bogdan' in html
    assert 'YTD' in html                       # bloc YTD per agent
    assert 'progress-bar' in html              # elemente vizuale de status
    assert 'Total bonus echip' in html         # total pe echipă (lună + YTD)
    assert 'Total bonus lun' in html           # footer total per agent


def test_gate_blocks_whole_month_end_to_end(app_client, seed_bogdan):
    """Vânzări 5000/10000 = 50% → toate KPI-urile se plătesc cu 0."""
    import json
    from queries.bonus import save_obiective, obiective, istoric_get
    from blueprints.bonus import build_agent_month
    save_obiective(2026, 6, 'Bogdan', 4000.0, 0.20, [
        {"tip": "vanzari", "referinta": None, "target": 10000.0,
         "unitate": "ron", "pondere": 0.5},
        {"tip": "incasari", "referinta": None, "target": 1000.0,
         "unitate": "ron", "pondere": 0.5},
    ])
    out = build_agent_month('Bogdan', 'DRAGNEA BOGDAN', 2026, 6)
    assert out['gate_vanzari'] is True
    assert out['total_bonus'] == 0.0

    # pagina anunță blocajul
    html = app_client.get('/bonus?an=2026&luna=6').get_data(as_text=True)
    assert 'Bonus blocat' in html

    # închiderea îngheață rezultatul blocat, chiar cu încasările la 100%
    kpi_id = [k for k in obiective(2026, 6, 'Bogdan') if k['tip'] == 'incasari'][0]['id']
    resp = app_client.post('/bonus/inchidere/lock', json={
        "an": 2026, "luna": 6, "agent_key": "Bogdan", "penalty": 0.0,
        "grad_incasare": 1.0, "note": "", "manual": {str(kpi_id): 1000.0}})
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    snap = json.loads(istoric_get(2026, 6, 'Bogdan')['lunar_data'])
    assert snap['gate_vanzari'] is True
    assert snap['total_bonus'] == 0.0
    assert all(k['bonus'] == 0.0 for k in snap['kpis'])


@pytest.mark.parametrize('url', ['/bonus?an=2026&luna=6', '/bonus/obiective?an=2026&luna=7',
                                 '/bonus/inchidere?an=2026&luna=6'])
def test_gate_rule_written_in_description(app_client, url):
    from bonus_calc import SALES_GATE
    html = app_client.get(url).get_data(as_text=True)
    assert 'Poartă vânzări' in html
    assert '%d%%' % int(SALES_GATE * 100) in html


@pytest.fixture
def reset_gate():
    """Readuce pragul lui Bogdan la implicit după test."""
    yield
    from queries.bonus import set_agent_sales_gate
    set_agent_sales_gate('Bogdan', None)


def test_sales_gate_per_agent_roundtrip(app_client, reset_gate):
    from queries.bonus import sales_gate
    from bonus_calc import SALES_GATE
    assert sales_gate('Bogdan') == SALES_GATE          # fără setare → implicit
    assert sales_gate('_inexistent_') == SALES_GATE

    resp = app_client.post('/bonus/config/agent/Bogdan/gate', json={'gate_pct': 60})
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    assert sales_gate('Bogdan') == 0.60

    # gol → revine la implicitul din cod
    app_client.post('/bonus/config/agent/Bogdan/gate', json={'gate_pct': ''})
    assert sales_gate('Bogdan') == SALES_GATE


def test_sales_gate_rejects_out_of_range(app_client, reset_gate):
    from queries.bonus import sales_gate
    from bonus_calc import SALES_GATE
    resp = app_client.post('/bonus/config/agent/Bogdan/gate', json={'gate_pct': 250})
    assert resp.status_code == 400 and resp.get_json()['ok'] is False
    resp = app_client.post('/bonus/config/agent/Bogdan/gate', json={'gate_pct': 'abc'})
    assert resp.status_code == 400
    assert sales_gate('Bogdan') == SALES_GATE


def test_agent_gate_applied_in_calculation(app_client, seed_bogdan, reset_gate):
    """Vânzări 5000/10000 = 50%: blocat la 80%, permis cu pragul agentului la 40%."""
    from queries.bonus import save_obiective, set_agent_sales_gate
    from blueprints.bonus import build_agent_month
    save_obiective(2026, 6, 'Bogdan', 4000.0, 0.20, [
        {"tip": "vanzari", "referinta": None, "target": 10000.0,
         "unitate": "ron", "pondere": 1.0}])
    assert build_agent_month('Bogdan', 'DRAGNEA BOGDAN', 2026, 6)['gate_vanzari'] is True

    set_agent_sales_gate('Bogdan', 0.40)
    out = build_agent_month('Bogdan', 'DRAGNEA BOGDAN', 2026, 6)
    assert out['gate_vanzari'] is False
    assert out['gate_prag'] == 0.40
    assert out['total_bonus'] == 0.0   # 50% realizare → treapta 0 din grilă

    set_agent_sales_gate('Bogdan', 0.0)   # 0 = poartă dezactivată
    assert build_agent_month('Bogdan', 'DRAGNEA BOGDAN', 2026, 6)['gate_vanzari'] is False


def test_config_page_shows_gate_input(app_client):
    html = app_client.get('/bonus/config').get_data(as_text=True)
    assert 'Poartă vânzări' in html
    assert 'id="gate-Bogdan"' in html
