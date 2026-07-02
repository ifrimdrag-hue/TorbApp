import sqlite3

try:
    from flask import g, has_app_context
except ImportError:
    g = None
    def has_app_context():
        return False

from app.paths import DB_PATH

# Pragmas aplicate la fiecare conexiune. WAL + cache mare + mmap reduc
# semnificativ I/O când baza e pe Google Drive (sync folder).
_PER_CONN_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA busy_timeout=5000",     # wait up to 5s on write lock instead of failing
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-65536",     # 64 MB page cache
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=268435456",   # 256 MB memory-mapped IO
)


def _new_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    for p in _PER_CONN_PRAGMAS:
        try:
            conn.execute(p)
        except sqlite3.DatabaseError:
            pass
    return conn


def _conn():
    """Reuse one connection per Flask request; create transient one in scripts."""
    if has_app_context():
        if 'db' not in g:
            g.db = _new_connection()
        return g.db
    return _new_connection()


def close_request_db(exc=None):
    """Hook for Flask teardown_appcontext."""
    if has_app_context():
        db = g.pop('db', None)
        if db is not None:
            db.close()


def query(sql, params=None):
    """Execute SQL, return list of dicts."""
    conn = _conn()
    transient = not has_app_context()
    try:
        cur = conn.execute(sql, params or {})
        return [dict(row) for row in cur.fetchall()]
    finally:
        if transient:
            conn.close()


def query_one(sql, params=None):
    rows = query(sql, params)
    return rows[0] if rows else None


def get_db():
    """Return a fresh connection for write operations (caller must commit/close).

    NOTE: returns a transient connection (not the request-scoped one) because
    callers manage `.close()` themselves; closing the request-scoped connection
    would break subsequent reads in the same request.
    """
    return _new_connection()
