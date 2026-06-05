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

# ── Build schema via the versioned migration runner (always in sync) ─────────
sys.path.insert(0, os.path.join(ROOT, 'migrations'))
from runner import run_all as _run_all  # noqa: E402
_run_all(_TEST_DB)

_conn = sqlite3.connect(_TEST_DB)

# Seed tari_export (required by clienti_export FK)
_conn.execute("INSERT OR IGNORE INTO tari_export (tara, piata) VALUES ('Ungaria','HU')")

# Seed minimal transactions so dashboard KPI queries return numbers, not None
_SEED_TX = [
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


@pytest.fixture(scope='session')
def db_path():
    return _TEST_DB
