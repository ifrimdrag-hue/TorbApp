"""
Migration 0038 — drop the CHECK(role IN ('admin','manager','viewer')) on adm_users.

Migration 0037 introduced dynamic, DB-backed roles (adm_roles/adm_role_nav) so
any custom role name (e.g. 'contabil', 'limited') can be granted nav access.
But the ALTER TABLE RENAME in 0037 carried over adm_users' original CHECK
constraint from migration 0002 verbatim, which still hardcodes the three
legacy role names — so INSERT OR IGNORE silently drops any adm_users row
whose role isn't admin/manager/viewer, defeating the whole point of dynamic
roles. SQLite cannot drop a CHECK constraint in place — rebuild the table
(same columns, same ids), following the same pattern as migration 0020.

FK note: password_reset_tokens.user_id and auth_log.user_id reference
adm_users(id). Enforcement is disabled for the rebuild; ids are preserved so
child rows stay valid.
"""

VERSION = 38
NAME = "0038_20260707_adm_users_drop_role_check"


def up(conn):
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("""
        CREATE TABLE adm_users_new (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            username       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            email          TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            password_hash  TEXT    NOT NULL,
            role           TEXT    NOT NULL DEFAULT 'manager',
            is_active      INTEGER NOT NULL DEFAULT 1,
            force_pw_reset INTEGER NOT NULL DEFAULT 0,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login_at  DATETIME
        )
    """)
    conn.execute("""
        INSERT INTO adm_users_new (
            id, username, email, password_hash, role, is_active,
            force_pw_reset, created_at, updated_at, last_login_at
        )
        SELECT
            id, username, email, password_hash, role, is_active,
            force_pw_reset, created_at, updated_at, last_login_at
        FROM adm_users
    """)
    conn.execute("DROP TABLE adm_users")
    conn.execute("ALTER TABLE adm_users_new RENAME TO adm_users")
