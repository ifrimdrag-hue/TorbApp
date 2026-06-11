"""Server-side cache for eMAG/Shopify connection status (connDot).

At most one upstream connection check per platform per TTL window,
shared across all users. Status rows live in the connection_status table
(migration 0010). Failures are cached the same as successes so a down
API is probed at most once per TTL.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from paths import DB_PATH

DEFAULT_TTL_SECONDS = 180


async def get_status(platform, refresh_fn, ttl=DEFAULT_TTL_SECONDS):
    """Return connection status for platform, cached up to ttl seconds.

    refresh_fn: async callable returning the payload dict, e.g.
    {'ok': True, 'locations': [...]} or {'ok': False, 'error': '...'}.
    It must not raise — wrap exceptions into {'ok': False, 'error': str(exc)}.

    The returned dict additionally carries 'cached' (bool) and
    'checked_at' (ISO-8601 UTC string).
    """
    now = datetime.now(timezone.utc)

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT payload, checked_at FROM connection_status WHERE platform=?",
            (platform,),
        ).fetchone()

    if row:
        try:
            checked = datetime.fromisoformat(row[1])
        except ValueError:
            checked = None
        if checked and now - checked < timedelta(seconds=ttl):
            payload = json.loads(row[0])
            payload['cached'] = True
            payload['checked_at'] = row[1]
            return payload

    payload = dict(await refresh_fn())
    checked_at = now.isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO connection_status (platform, ok, payload, checked_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(platform) DO UPDATE SET"
            " ok=excluded.ok, payload=excluded.payload, checked_at=excluded.checked_at",
            (platform, 1 if payload.get('ok') else 0, json.dumps(payload), checked_at),
        )
    payload['cached'] = False
    payload['checked_at'] = checked_at
    return payload
