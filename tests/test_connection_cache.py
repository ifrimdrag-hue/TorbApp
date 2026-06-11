import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from connection_cache import get_status


def _seed(db_path, platform, ok, payload, age_seconds):
    """Insert/replace a connection_status row checked age_seconds ago."""
    checked_at = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    with sqlite3.connect(db_path) as c:
        c.execute(
            "INSERT INTO connection_status (platform, ok, payload, checked_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(platform) DO UPDATE SET"
            " ok=excluded.ok, payload=excluded.payload, checked_at=excluded.checked_at",
            (platform, ok, json.dumps(payload), checked_at),
        )


def test_fresh_cache_skips_refresh(db_path):
    _seed(db_path, 'p_fresh', 1, {'ok': True}, age_seconds=10)
    calls = []

    async def refresh():
        calls.append(1)
        return {'ok': True}

    result = asyncio.run(get_status('p_fresh', refresh))
    assert result['ok'] is True
    assert result['cached'] is True
    assert 'checked_at' in result
    assert calls == []


def test_stale_cache_calls_refresh_and_upserts(db_path):
    _seed(db_path, 'p_stale', 0, {'ok': False, 'error': 'old'}, age_seconds=600)

    async def refresh():
        return {'ok': True}

    result = asyncio.run(get_status('p_stale', refresh))
    assert result['ok'] is True
    assert result['cached'] is False

    with sqlite3.connect(db_path) as c:
        row = c.execute(
            "SELECT ok, payload FROM connection_status WHERE platform='p_stale'"
        ).fetchone()
    assert row[0] == 1
    assert json.loads(row[1])['ok'] is True


def test_missing_row_calls_refresh_and_inserts(db_path):
    async def refresh():
        return {'ok': True, 'locations': [{'id': 1}]}

    result = asyncio.run(get_status('p_missing', refresh))
    assert result['ok'] is True
    assert result['cached'] is False
    assert result['locations'] == [{'id': 1}]

    with sqlite3.connect(db_path) as c:
        row = c.execute(
            "SELECT ok FROM connection_status WHERE platform='p_missing'"
        ).fetchone()
    assert row is not None
    assert row[0] == 1


def test_error_result_is_cached(db_path):
    calls = []

    async def refresh():
        calls.append(1)
        return {'ok': False, 'error': 'API down'}

    first = asyncio.run(get_status('p_err', refresh))
    second = asyncio.run(get_status('p_err', refresh))
    assert first['cached'] is False
    assert second['cached'] is True
    assert second['ok'] is False
    assert second['error'] == 'API down'
    assert calls == [1]


def test_custom_ttl_expires(db_path):
    _seed(db_path, 'p_ttl', 1, {'ok': True}, age_seconds=30)

    async def refresh():
        return {'ok': False, 'error': 'rechecked'}

    result = asyncio.run(get_status('p_ttl', refresh, ttl=20))
    assert result['cached'] is False
    assert result['ok'] is False
