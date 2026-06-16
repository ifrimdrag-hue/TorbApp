"""Tests for bonus DB schema and query layer (app/queries/bonus.py)."""
import sys
import os
import sqlite3
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import paths
from db import query


def test_bonus_tables_exist():
    names = {r['name'] for r in query(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'bonus_config', 'bonus_lunar_config', 'bonus_obiective_strategice',
            'bonus_payout_grid', 'bonus_istoric'} <= names


def test_realizat_manual_column_exists():
    cols = {r['name'] for r in query("PRAGMA table_info(bonus_obiective_strategice)")}
    assert 'realizat_manual' in cols


def test_default_payout_grid_seeded():
    rows = query("SELECT threshold, multiplier FROM bonus_payout_grid "
                 "WHERE agent_key='_default' ORDER BY threshold")
    assert (rows[0]['threshold'], rows[0]['multiplier']) == (0.0, 0.0)
    assert (rows[-1]['threshold'], rows[-1]['multiplier']) == (1.2, 1.5)


def test_bonus_agents_returns_field_agents():
    from queries.bonus import bonus_agents
    keys = {a['agent_key'] for a in bonus_agents()}
    assert {'Bogdan', 'Claudiu', 'Oana', 'Ionut'} <= keys
    assert 'Teo' not in keys

def test_payout_grid_falls_back_to_default():
    from queries.bonus import payout_grid
    g = payout_grid('AgentInexistent')
    assert g[0] == (0.0, 0.0)
    assert g[-1] == (1.2, 1.5)


@pytest.fixture
def seed_tx():
    """Inserează tranzacții deterministe pentru un agent de test și curăță după."""
    conn = sqlite3.connect(paths.DB_PATH)
    rows = [
        (2025, 6, '2025-06-10', 'TESTAGENT', 'Basilur', 'Client A', 'CA', 1000.0, 300.0),
        (2025, 6, '2025-06-12', 'TESTAGENT', 'Toras',   'Client B', 'CB', 500.0,  100.0),
        (2026, 6, '2026-06-10', 'TESTAGENT', 'Basilur', 'Client A', 'CA', 1200.0, 400.0),
        (2026, 6, '2026-06-11', 'TESTAGENT', 'Basilur', 'Client C', 'CC', 800.0,  200.0),
    ]
    conn.executemany(
        "INSERT INTO tranzactii (an, luna, data_dl, agent, furnizor, client, "
        "cod_client, val_neta, marja_bruta) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(paths.DB_PATH)
    conn.execute("DELETE FROM tranzactii WHERE agent='TESTAGENT'")
    conn.commit()
    conn.close()


def test_realizat_auto_vanzari_marja(seed_tx):
    from queries.bonus import realizat_auto
    r = realizat_auto('TESTAGENT', 2026, 6)
    assert r['vanzari'] == 2000.0
    assert r['marja'] == 600.0
    assert r['clienti'] == 2

def test_realizat_brand(seed_tx):
    from queries.bonus import realizat_brand
    assert realizat_brand('TESTAGENT', 'Basilur', 2026, 6) == 2000.0

def test_py_baseline_same_month(seed_tx):
    from queries.bonus import py_baseline
    b = py_baseline('TESTAGENT', 2026, 6)
    assert b['vanzari'] == 1500.0
    assert b['brand']['Basilur'] == 1000.0
