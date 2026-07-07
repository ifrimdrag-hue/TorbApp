import sqlite3
import importlib.util
from pathlib import Path

MIG = Path(__file__).resolve().parents[1] / "migrations" / "0037_20260707_admin_rbac.py"


def _load():
    spec = importlib.util.spec_from_file_location("mig0037", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _base_db(path):
    """Minimal pre-0037 schema: a users table like migration 0002 leaves."""
    c = sqlite3.connect(path)
    c.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY, username TEXT, email TEXT,
            password_hash TEXT, role TEXT, is_active INTEGER DEFAULT 1,
            force_pw_reset INTEGER DEFAULT 0, last_login_at TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE auth_log (id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id), event TEXT);
        """
    )
    c.commit()
    return c


def test_migration_creates_tables_renames_and_seeds(tmp_path):
    db = str(tmp_path / "t.db")
    conn = _base_db(db)
    mod = _load()
    mod.up(conn)
    conn.commit()

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "adm_users" in tables and "users" not in tables
    assert "adm_roles" in tables and "adm_role_nav" in tables

    roles = dict(conn.execute("SELECT name, is_system FROM adm_roles").fetchall())
    assert roles == {"admin": 1, "manager": 1, "viewer": 1}

    from importlib import import_module
    import sys
    sys.path.insert(0, str(MIG.resolve().parents[1] / "app"))
    reg = import_module("nav_registry")
    all_keys = {i.key for i in reg.NAV_REGISTRY}
    for role in ("manager", "viewer"):
        rid = conn.execute("SELECT id FROM adm_roles WHERE name=?", (role,)).fetchone()[0]
        granted = {r[0] for r in conn.execute(
            "SELECT nav_key FROM adm_role_nav WHERE role_id=?", (rid,))}
        assert granted == all_keys, f"{role} should be seeded with every nav key"
    # admin gets no rows (bypassed)
    aid = conn.execute("SELECT id FROM adm_roles WHERE name='admin'").fetchone()[0]
    assert conn.execute(
        "SELECT COUNT(*) FROM adm_role_nav WHERE role_id=?", (aid,)).fetchone()[0] == 0


def test_migration_is_idempotent(tmp_path):
    db = str(tmp_path / "t.db")
    conn = _base_db(db)
    mod = _load()
    mod.up(conn)
    conn.commit()
    mod.up(conn)  # second run must not raise
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM adm_roles").fetchone()[0] == 3
