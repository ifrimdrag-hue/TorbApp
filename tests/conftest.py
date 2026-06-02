"""
Shared pytest fixtures.

Creates a temp SQLite DB with the full schema and patches DB_PATH before
the Flask app is imported, so all tests run against an in-memory-equivalent
isolated database (no dependency on data/torb.db).
"""
import sys
import os
import sqlite3
import tempfile
import atexit
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))

# ── Create temp DB and patch DB_PATH BEFORE any app module is imported ──────
_tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
_tmp.close()
_TEST_DB = _tmp.name
atexit.register(lambda: os.unlink(_TEST_DB) if os.path.exists(_TEST_DB) else None)

import paths as _paths_mod  # noqa: E402
_paths_mod.DB_PATH = _TEST_DB

import db as _db_mod  # noqa: E402
_db_mod.DB_PATH = _TEST_DB

import db_stock as _db_stock_mod  # noqa: E402
_db_stock_mod.DB_PATH = _TEST_DB

# ── Full schema (all tables the app reads/writes) ────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS tranzactii (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    luna            INTEGER,
    an              INTEGER,
    data_dl         TEXT,
    nr_dl           TEXT,
    nr_factura      TEXT,
    nr_comanda      TEXT,
    cod_produs      TEXT,
    sku             TEXT,
    furnizor        TEXT,
    um              TEXT,
    cantitate       REAL,
    pret_vanzare    REAL,
    tva_pct         REAL,
    pret_cumparare  REAL,
    val_bruta       REAL,
    val_neta        REAL,
    val_achizitie   REAL,
    val_usd         REAL,
    marja_bruta     REAL,
    discount_pct    REAL,
    discount_val    REAL,
    client          TEXT,
    cod_client      TEXT,
    cui_client      TEXT,
    tip_client      TEXT,
    oras_client     TEXT,
    judet_client    TEXT,
    adresa_client   TEXT,
    agent           TEXT,
    adr_livrare     TEXT,
    locatie         TEXT,
    UNIQUE(nr_dl, cod_produs, nr_factura, pret_vanzare)
);
CREATE TABLE IF NOT EXISTS stoc (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    data_snapshot   TEXT NOT NULL,
    cod_produs      TEXT,
    cod_mare        TEXT,
    sku             TEXT,
    furnizor        TEXT,
    gama            TEXT,
    cantitate       REAL,
    pret_achizitie  REAL,
    data_intrare    TEXT,
    nr_zile_stoc    INTEGER,
    greutate        REAL,
    um              TEXT DEFAULT 'BUC',
    cod_sortiment   TEXT,
    codbare         TEXT,
    piata           TEXT DEFAULT 'RO',
    UNIQUE(data_snapshot, cod_produs, data_intrare)
);
CREATE VIEW IF NOT EXISTS v_sku_cod AS
    SELECT sku, cod_produs AS cod FROM tranzactii
    WHERE sku IS NOT NULL AND cod_produs IS NOT NULL GROUP BY sku;
CREATE VIEW IF NOT EXISTS v_vanzari_luna_furnizor AS
    SELECT an, luna, furnizor,
        ROUND(SUM(val_neta), 2) AS val_neta,
        ROUND(SUM(marja_bruta), 2) AS marja_bruta,
        ROUND(SUM(marja_bruta)*100.0/NULLIF(SUM(val_neta),0), 2) AS marja_pct,
        SUM(cantitate) AS cantitate
    FROM tranzactii GROUP BY an, luna, furnizor;
CREATE VIEW IF NOT EXISTS v_vanzari_luna_agent AS
    SELECT an, luna, agent,
        ROUND(SUM(val_neta), 2) AS val_neta,
        ROUND(SUM(marja_bruta), 2) AS marja_bruta,
        ROUND(SUM(marja_bruta)*100.0/NULLIF(SUM(val_neta),0), 2) AS marja_pct
    FROM tranzactii GROUP BY an, luna, agent;
CREATE VIEW IF NOT EXISTS v_vanzari_luna_client AS
    SELECT an, luna, client, cod_client, tip_client, oras_client, judet_client,
        ROUND(SUM(val_neta), 2) AS val_neta,
        ROUND(SUM(marja_bruta), 2) AS marja_bruta,
        ROUND(SUM(marja_bruta)*100.0/NULLIF(SUM(val_neta),0), 2) AS marja_pct
    FROM tranzactii GROUP BY an, luna, client;
CREATE VIEW IF NOT EXISTS v_vanzari_an_furnizor AS
    SELECT an, furnizor,
        ROUND(SUM(val_neta), 2) AS val_neta,
        ROUND(SUM(val_achizitie), 2) AS val_achizitie,
        ROUND(SUM(marja_bruta), 2) AS marja_bruta,
        ROUND(SUM(marja_bruta)*100.0/NULLIF(SUM(val_neta),0), 2) AS marja_pct,
        COUNT(DISTINCT client) AS nr_clienti,
        COUNT(DISTINCT cod_produs) AS nr_sku
    FROM tranzactii GROUP BY an, furnizor;
CREATE VIEW IF NOT EXISTS v_top_sku AS
    SELECT an, furnizor, cod_produs, sku,
        ROUND(SUM(val_neta), 2) AS val_neta,
        ROUND(SUM(marja_bruta), 2) AS marja_bruta,
        SUM(cantitate) AS cantitate,
        COUNT(DISTINCT client) AS nr_clienti
    FROM tranzactii GROUP BY an, furnizor, cod_produs, sku;
CREATE VIEW IF NOT EXISTS v_clienti AS
    SELECT client, cod_client, cui_client, tip_client, oras_client, judet_client,
        MIN(data_dl) AS prima_comanda, MAX(data_dl) AS ultima_comanda,
        ROUND(SUM(val_neta), 2) AS val_neta_total,
        ROUND(SUM(marja_bruta), 2) AS marja_totala,
        COUNT(DISTINCT nr_factura) AS nr_facturi,
        COUNT(DISTINCT furnizor) AS nr_branduri,
        agent AS agent_principal
    FROM tranzactii GROUP BY client;
CREATE TABLE IF NOT EXISTS cond_resolved (
    an          INTEGER NOT NULL,
    cod_client  TEXT    NOT NULL,
    furnizor    TEXT    NOT NULL,
    eff_pct     REAL    NOT NULL DEFAULT 0,
    eff_fixed   REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (an, cod_client, furnizor)
);
CREATE TABLE IF NOT EXISTS conditii_comerciale (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    an            INTEGER NOT NULL,
    cod_client    TEXT,
    furnizor      TEXT,
    tip_valoare   TEXT NOT NULL CHECK(tip_valoare IN ('pct','suma_fixa')),
    periodicitate TEXT NOT NULL CHECK(periodicitate IN ('lunar','anual','unic')),
    valoare       REAL NOT NULL,
    descriere     TEXT,
    data_creare   TEXT
);
CREATE TABLE IF NOT EXISTS termene_plata (
    id INTEGER PRIMARY KEY AUTOINCREMENT, an INTEGER NOT NULL,
    cod_client TEXT NOT NULL, zile_termen INTEGER NOT NULL,
    observatii TEXT, data_creare TEXT
);
CREATE TABLE IF NOT EXISTS produse (
    sku TEXT PRIMARY KEY, descriere TEXT, furnizor TEXT, brand TEXT,
    categorie TEXT, gramaj REAL, buc_cutie INTEGER, ean TEXT,
    tva_pct REAL DEFAULT 0.09, hs_code TEXT,
    taxa_vamala_mfn_pct REAL DEFAULT 0, taxa_vamala_pct REAL DEFAULT 0,
    origine TEXT DEFAULT 'import_extraeu', tara_origine TEXT,
    activ INTEGER DEFAULT 1, gama TEXT
);
CREATE TABLE IF NOT EXISTS rate_schimb (
    id INTEGER PRIMARY KEY AUTOINCREMENT, an INTEGER NOT NULL,
    moneda TEXT NOT NULL, curs_ron REAL NOT NULL, UNIQUE(an, moneda)
);
CREATE TABLE IF NOT EXISTS costuri_landing (
    id INTEGER PRIMARY KEY AUTOINCREMENT, an INTEGER NOT NULL, sku TEXT NOT NULL,
    moneda TEXT NOT NULL DEFAULT 'USD', pret_achizitie_valuta REAL,
    curs_ron REAL, pret_achizitie_ron REAL, transport_pct REAL DEFAULT 10.0,
    taxa_vamala_pct REAL DEFAULT 0.0, alte_costuri_ron REAL DEFAULT 0.0,
    landing_cost_ron REAL, UNIQUE(an, sku)
);
CREATE TABLE IF NOT EXISTS preturi_vanzare (
    id INTEGER PRIMARY KEY AUTOINCREMENT, an INTEGER NOT NULL, sku TEXT NOT NULL,
    cod_client TEXT, pret_vanzare_ron REAL NOT NULL, activ INTEGER DEFAULT 1,
    UNIQUE(an, sku, cod_client)
);
CREATE TABLE IF NOT EXISTS termene_aprovizionare (
    id INTEGER PRIMARY KEY AUTOINCREMENT, furnizor TEXT NOT NULL,
    zile_livrare INTEGER NOT NULL DEFAULT 30, sezon_craciun INTEGER NOT NULL DEFAULT 0,
    observatii TEXT, zile_livrare_min INTEGER DEFAULT 30,
    moneda TEXT DEFAULT 'EUR', tip_produs TEXT DEFAULT 'Altele', UNIQUE(furnizor)
);
CREATE TABLE IF NOT EXISTS comenzi_furnizori (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr_comanda TEXT, furnizor TEXT NOT NULL,
    data_comanda DATE NOT NULL DEFAULT (date('now')),
    status TEXT NOT NULL DEFAULT 'Emisa',
    data_estimata_livrare DATE, eta DATE, data_confirmare_furnizor DATE,
    observatii TEXT, total_usd REAL, moneda TEXT, file_source TEXT,
    zile_livrare_estimat INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS comenzi_furnizori_linii (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comanda_id INTEGER NOT NULL REFERENCES comenzi_furnizori(id) ON DELETE CASCADE,
    sku TEXT NOT NULL, cantitate_sugerat INTEGER DEFAULT 0,
    cantitate_comandata INTEGER NOT NULL DEFAULT 0,
    cantitate_ro INTEGER DEFAULT 0, cantitate_export INTEGER DEFAULT 0,
    cantitate_confirmata INTEGER, cod_furnizor TEXT, units_per_carton INTEGER,
    cantitate_baxuri REAL, gross_kg REAL, net_kg REAL, cbm REAL,
    total_valuta REAL, descriere TEXT, pret_valuta REAL,
    moneda TEXT DEFAULT 'EUR', observatii TEXT
);
CREATE TABLE IF NOT EXISTS tari_export (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tara TEXT NOT NULL UNIQUE,
    piata TEXT NOT NULL DEFAULT 'HU' CHECK(piata IN ('RO','HU')),
    activ INTEGER DEFAULT 1, observatii TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS clienti_export (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tara_id INTEGER NOT NULL REFERENCES tari_export(id),
    cod_client TEXT NOT NULL UNIQUE, nume_client TEXT NOT NULL,
    activ INTEGER DEFAULT 1, observatii TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS echipa (
    employee_id TEXT PRIMARY KEY, nume TEXT, rol TEXT,
    raporteaza_la_id TEXT, activ INTEGER,
    bonus_target_lunar_ron REAL, bonus_target_trim_ron REAL, observatii TEXT
);
CREATE TABLE IF NOT EXISTS targeturi_kpi (
    id INTEGER PRIMARY KEY AUTOINCREMENT, an INTEGER, luna INTEGER,
    employee_id TEXT, net_sales REAL, gross_margin REAL, active_clients REAL,
    focus_mix REAL, collections REAL, promo_exec REAL, forecast REAL,
    strategic REAL, pharma_sales REAL, team_sales REAL, team_margin REAL,
    team_active_clients REAL, UNIQUE(an, luna, employee_id)
);
CREATE TABLE IF NOT EXISTS actuale_kpi (
    id INTEGER PRIMARY KEY AUTOINCREMENT, an INTEGER, luna INTEGER,
    employee_id TEXT, net_sales REAL, gross_margin REAL, active_clients REAL,
    focus_mix REAL, collections REAL, promo_exec REAL, forecast REAL,
    strategic REAL, pharma_sales REAL, team_sales REAL, team_margin REAL,
    team_active_clients REAL, penalizare_erori_pct REAL,
    UNIQUE(an, luna, employee_id)
);
CREATE TABLE IF NOT EXISTS targeturi_cantitativ (
    id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, client TEXT, sku TEXT,
    an INTEGER, luna INTEGER, cantitate REAL,
    UNIQUE(agent, client, sku, an, luna)
);
CREATE TABLE IF NOT EXISTS stoc_expirare (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cod_produs TEXT NOT NULL,
    sku TEXT NOT NULL, furnizor TEXT, gama TEXT, data_intrare TEXT,
    data_expirare TEXT, lot TEXT, cantitate REAL, pret_achizitie REAL,
    data_snapshot TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tip TEXT NOT NULL, fisier TEXT,
    randuri INTEGER, durata_s REAL, status TEXT NOT NULL, mesaj TEXT,
    creat_la TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email          TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'manager'
                   CHECK(role IN ('admin','manager','viewer')),
    is_active      INTEGER NOT NULL DEFAULT 1,
    force_pw_reset INTEGER NOT NULL DEFAULT 0,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login_at  DATETIME
);
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE, expires_at DATETIME NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS auth_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id),
    event TEXT NOT NULL, ip_address TEXT, details TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

_conn = sqlite3.connect(_TEST_DB)
_conn.executescript(_SCHEMA)

# Seed tari_export (required by clienti_export FK)
_conn.execute("INSERT OR IGNORE INTO tari_export (tara, piata) VALUES ('Ungaria','HU')")

# Seed minimal transactions so dashboard KPI queries return numbers, not None
_SEED_TX = [
    # (luna, an, data_dl, nr_dl, nr_factura, cod_produs, sku, furnizor,
    #  cantitate, pret_vanzare, tva_pct, pret_cumparare,
    #  val_bruta, val_neta, val_achizitie, marja_bruta, discount_pct,
    #  client, cod_client, agent)
    (1, 2026, '2026-01-15', 'DL001', 'F001', 'P001', 'SKU001', 'Basilur',
     10, 50.0, 0.09, 30.0, 545.0, 500.0, 300.0, 200.0, 0.0,
     'Client Test', 'C001', 'Agent Test'),
    (1, 2026, '2026-01-20', 'DL002', 'F002', 'P002', 'SKU002', 'Toras',
     5, 80.0, 0.09, 50.0, 436.0, 400.0, 250.0, 150.0, 0.0,
     'KAUFLAND ROMANIA', 'KAUFLAND', 'Agent Test'),
]
for tx in _SEED_TX:
    _conn.execute("""
        INSERT OR IGNORE INTO tranzactii
        (luna, an, data_dl, nr_dl, nr_factura, cod_produs, sku, furnizor,
         cantitate, pret_vanzare, tva_pct, pret_cumparare,
         val_bruta, val_neta, val_achizitie, marja_bruta, discount_pct,
         client, cod_client, agent)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, tx)

from werkzeug.security import generate_password_hash  # noqa: E402

_conn.execute(
    "INSERT OR IGNORE INTO users (username, email, password_hash, role) VALUES (?,?,?,?)",
    ('testadmin', 'test@test.local', generate_password_hash('testpass'), 'admin'),
)
_conn.commit()
_conn.close()


@pytest.fixture(scope='session')
def flask_app():
    import app as flask_module
    a = flask_module.create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False})
    return a


@pytest.fixture(scope='session')
def client(flask_app):
    c = flask_app.test_client()
    # Log in once for the whole session — all route tests expect an authenticated user
    rv = c.post('/auth/login', data={'username': 'testadmin', 'password': 'testpass'})
    assert rv.status_code == 302, f"Test login failed (status {rv.status_code}) — check test DB seeding"
    return c
