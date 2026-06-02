import os
import sqlite3
from flask import g

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'stock.db'
)


def _new_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _conn():
    if '_stock_db' not in g:
        g._stock_db = _new_connection()
    return g._stock_db


def close_request_db_stock(exc=None):
    db = g.pop('_stock_db', None)
    if db is not None:
        db.close()


def query(sql, params=None):
    cur = _conn().execute(sql, params or [])
    return [dict(r) for r in cur.fetchall()]


def query_one(sql, params=None):
    cur = _conn().execute(sql, params or [])
    row = cur.fetchone()
    return dict(row) if row else None


def get_db():
    return _conn()
