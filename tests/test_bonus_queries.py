"""Tests for bonus DB schema and query layer (app/queries/bonus.py)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

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
