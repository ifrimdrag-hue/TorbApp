"""Migration 0037 — Admin RBAC: dynamic roles + nav authorization.

Creates adm_roles + adm_role_nav, renames users -> adm_users (SQLite >=3.25
auto-rewrites child FK references), seeds the three system roles, and grants
every current nav key to manager + viewer so day-one behavior is unchanged.
admin is a superuser and intentionally receives no grant rows.
"""
import os
import sys

VERSION = 37
NAME = "0037_20260707_admin_rbac"


def _nav_keys():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "app"))
    from nav_registry import NAV_REGISTRY
    return [item.key for item in NAV_REGISTRY]


def up(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS adm_roles (
            id         INTEGER PRIMARY KEY,
            name       TEXT NOT NULL UNIQUE,
            label      TEXT NOT NULL,
            is_system  INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS adm_role_nav (
            role_id INTEGER NOT NULL REFERENCES adm_roles(id) ON DELETE CASCADE,
            nav_key TEXT NOT NULL,
            PRIMARY KEY (role_id, nav_key)
        );
        """
    )

    # Rename users -> adm_users, guarded so re-runs are safe.
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "users" in names and "adm_users" not in names:
        conn.execute("ALTER TABLE users RENAME TO adm_users")

    conn.executemany(
        "INSERT OR IGNORE INTO adm_roles (name, label, is_system) VALUES (?,?,1)",
        [("admin", "Admin"), ("manager", "Manager"), ("viewer", "Viewer")],
    )

    keys = _nav_keys()
    for role in ("manager", "viewer"):
        rid = conn.execute("SELECT id FROM adm_roles WHERE name=?", (role,)).fetchone()[0]
        conn.executemany(
            "INSERT OR IGNORE INTO adm_role_nav (role_id, nav_key) VALUES (?,?)",
            [(rid, k) for k in keys],
        )
