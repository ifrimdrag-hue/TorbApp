"""
Migration 0002 — authentication tables and initial admin user.

Creates: users, password_reset_tokens, auth_log
Seeds:   admin user (username=admin, email=vlad.rosioru@gmail.com)
"""

VERSION = 2
NAME = "0002_20260523_add_auth"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            username       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            email          TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            password_hash  TEXT    NOT NULL,
            role           TEXT    NOT NULL DEFAULT 'manager'
                           CHECK(role IN ('admin','manager','viewer')),
            is_active      INTEGER NOT NULL DEFAULT 1,
            force_pw_reset INTEGER NOT NULL DEFAULT 0,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login_at  DATETIME
        );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT    NOT NULL UNIQUE,
            expires_at DATETIME NOT NULL,
            used       INTEGER  NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS auth_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER REFERENCES users(id),
            event      TEXT    NOT NULL,
            ip_address TEXT,
            details    TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    from werkzeug.security import generate_password_hash
    pw_hash = generate_password_hash("q1w2e3r4t5")
    conn.execute(
        """
        INSERT OR IGNORE INTO users (username, email, password_hash, role, force_pw_reset)
        VALUES (?, ?, ?, 'admin', 1)
        """,
        ("admin", "vlad.rosioru@gmail.com", pw_hash),
    )
