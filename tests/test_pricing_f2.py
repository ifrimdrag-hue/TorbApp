"""Pricing F2: manual article creation, simulator, price proposals."""
import sqlite3
import pytest


@pytest.fixture()
def seed_f2(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        INSERT OR IGNORE INTO produse (sku, descriere, furnizor, categorie,
            gama, activ) VALUES ('F2-1', 'Ceai test', 'Basilur', 'CEAI',
            'Basilur', 1);
        INSERT OR IGNORE INTO costuri_landing (an, sku, moneda,
            pret_achizitie_valuta, curs_ron, pret_achizitie_ron,
            transport_pct, taxa_vamala_pct, alte_costuri_ron, landing_cost_ron)
        VALUES (2026, 'F2-1', 'USD', 10.5, 4.6, 48.3, 0, 0, 0, 48.3);
        INSERT OR IGNORE INTO preturi_vanzare (an, sku, cod_client,
            pret_vanzare_ron, activ) VALUES (2026, 'F2-1', 'CL-F2', 60, 1);
        INSERT INTO tranzactii (an, cod_client, client, furnizor, sku)
        SELECT 2026, 'CL-F2', 'CLIENT F2 SRL', 'Basilur', 'F2-1'
        WHERE NOT EXISTS (SELECT 1 FROM tranzactii WHERE cod_client='CL-F2');
        DELETE FROM conditii_comerciale WHERE cod_client = 'CL-F2';
        INSERT INTO conditii_comerciale (an, cod_client, tip_valoare,
            periodicitate, valoare) VALUES (2026, 'CL-F2', 'pct', 'anual', 10);
    """)
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        DELETE FROM propuneri_pret_linii;
        DELETE FROM propuneri_pret;
        DELETE FROM conditii_comerciale WHERE cod_client = 'CL-F2';
    """)
    conn.commit()
    conn.close()


def test_articol_nou_page(client):
    rv = client.get('/preturi/nou')
    assert rv.status_code == 200
    assert 'Articol nou'.encode() in rv.data


def test_articol_nou_create_full(client, db_path):
    rv = client.post('/api/preturi/articol-nou', json={
        'sku': 'NOU-01', 'descriere': 'Articol test', 'furnizor': 'Basilur',
        'categorie': 'CEAI', 'gramaj': 100, 'buc_cutie': 24, 'tva_pct': 0.09,
        'poza_url': 'https://example.com/p.jpg',
        'logistica': {'buc_bax': 24, 'bax_l_mm': 400, 'bax_w_mm': 300,
                      'bax_h_mm': 200, 'bax_cbm': 0.024},
        'landing': {'an': 2026, 'moneda': 'USD', 'pret_valuta': 2,
                    'curs': 4.6, 'transport_pct': 10},
    })
    assert rv.status_code == 200 and rv.get_json()['ok']
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT descriere FROM produse WHERE sku='NOU-01'")\
        .fetchone()[0] == 'Articol test'
    assert conn.execute("SELECT buc_bax FROM produse_logistica WHERE sku='NOU-01'")\
        .fetchone()[0] == 24
    assert conn.execute("SELECT url_sursa FROM produse_media WHERE sku='NOU-01'")\
        .fetchone()[0] == 'https://example.com/p.jpg'
    landing = conn.execute(
        "SELECT landing_cost_ron FROM costuri_landing WHERE sku='NOU-01' AND an=2026")\
        .fetchone()[0]
    assert landing == pytest.approx(2 * 4.6 * 1.1, abs=0.01)
    conn.close()


def test_articol_nou_duplicate_rejected(client):
    rv = client.post('/api/preturi/articol-nou', json={
        'sku': 'NOU-01', 'descriere': 'x', 'furnizor': 'Basilur'})
    assert rv.status_code == 400
    assert 'exista deja' in rv.get_json()['error']


def test_simulator_page_renders(client, seed_f2):
    rv = client.get('/preturi/simulator?an=2026&client=CL-F2')
    assert rv.status_code == 200
    assert b'F2-1' in rv.data
    assert 'Simulator preț'.encode() in rv.data


def test_propunere_saved_with_engine_margins(client, seed_f2, db_path):
    rv = client.post('/api/preturi/propuneri', json={
        'an': 2026, 'cod_client': 'CL-F2', 'titlu': 'Test F2',
        'linii': [{'sku': 'F2-1', 'pret_propus': 69}],
    })
    data = rv.get_json()
    assert rv.status_code == 200 and data['ok'] and data['nr_linii'] == 1
    conn = sqlite3.connect(db_path)
    li = conn.execute(
        "SELECT pret_actual, landing_ron, cond_pct, marja_neta_pct, verdict "
        "FROM propuneri_pret_linii WHERE propunere_id=?", (data['id'],)).fetchone()
    conn.close()
    # gross 30% - 10% conditions = 20% net -> below the 25% approval floor
    assert li == (60, 48.3, 10, 20.0, 'aprobare_director')
    # detail endpoint
    rv = client.get(f"/api/preturi/propuneri/{data['id']}")
    assert rv.get_json()['linii'][0]['sku'] == 'F2-1'
    # delete cascades
    rv = client.delete(f"/api/preturi/propuneri/{data['id']}")
    assert rv.get_json()['ok']


def test_propunere_empty_rejected(client, seed_f2):
    rv = client.post('/api/preturi/propuneri', json={
        'an': 2026, 'cod_client': 'CL-F2', 'linii': []})
    assert rv.status_code == 400
