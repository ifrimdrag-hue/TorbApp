"""Tests for the DB backup/restore engine and the /admin/db routes."""
import gzip
import os
import sqlite3
import time

import pytest

import backup_db


def _make_db(path, marker):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS marker (val TEXT)")
    conn.execute("DELETE FROM marker")
    conn.execute("INSERT INTO marker VALUES (?)", (marker,))
    conn.commit()
    conn.close()


def _read_marker(path):
    conn = sqlite3.connect(path)
    val = conn.execute("SELECT val FROM marker").fetchone()[0]
    conn.close()
    return val


# ── Core engine ──────────────────────────────────────────────────────────────

def test_create_and_list_backup(tmp_path):
    db = str(tmp_path / "t.db")
    bdir = str(tmp_path / "backups")
    _make_db(db, "v1")

    path = backup_db.create_backup("manual", db_path=db, backup_dir=bdir)
    assert os.path.isfile(path)
    assert path.endswith(".db.gz")

    backups = backup_db.list_backups(bdir)
    assert len(backups) == 1
    assert backups[0]["tag"] == "manual"
    assert backups[0]["size"] > 0


def test_backup_is_valid_gzipped_sqlite(tmp_path):
    db = str(tmp_path / "t.db")
    bdir = str(tmp_path / "backups")
    _make_db(db, "v1")
    path = backup_db.create_backup("daily", db_path=db, backup_dir=bdir)

    raw = str(tmp_path / "unpacked.db")
    with gzip.open(path, "rb") as f_in, open(raw, "wb") as f_out:
        f_out.write(f_in.read())
    assert _read_marker(raw) == "v1"


def test_restore_round_trip(tmp_path):
    db = str(tmp_path / "t.db")
    bdir = str(tmp_path / "backups")
    _make_db(db, "before")
    backup = backup_db.create_backup("manual", db_path=db, backup_dir=bdir)

    _make_db(db, "after")
    assert _read_marker(db) == "after"

    safety = backup_db.restore_backup(
        os.path.basename(backup), db_path=db, backup_dir=bdir, run_migrations=False
    )
    assert _read_marker(db) == "before"
    # The pre-restore safety backup preserves the overwritten state
    assert "pre-restore" in safety
    assert os.path.isfile(os.path.join(bdir, safety))


def test_restore_rejects_bad_names(tmp_path):
    db = str(tmp_path / "t.db")
    _make_db(db, "v1")
    for bad in ("../../etc/passwd", "torb_evil.db.gz", "x.db.gz", ""):
        with pytest.raises(ValueError):
            backup_db.restore_backup(bad, db_path=db, backup_dir=str(tmp_path))


def test_create_backup_rejects_bad_tag(tmp_path):
    with pytest.raises(ValueError):
        backup_db.create_backup("nightly", db_path=str(tmp_path / "t.db"),
                                backup_dir=str(tmp_path))


def test_prune_keeps_recent_and_min_keep(tmp_path):
    bdir = str(tmp_path / "backups")
    os.makedirs(bdir)

    # Five expired backups (fake files — prune only looks at names and mtimes)
    old = time.time() - (backup_db.RETENTION_DAYS + 1) * 86400
    names = [f"torb_2026-01-0{i}_120000_daily.db.gz" for i in range(1, 6)]
    for n in names:
        full = os.path.join(bdir, n)
        with open(full, "wb") as f:
            f.write(b"x")
        os.utime(full, (old, old))

    deleted = backup_db.prune(bdir)
    remaining = [b["name"] for b in backup_db.list_backups(bdir)]
    assert len(remaining) == backup_db.MIN_KEEP  # never below MIN_KEEP
    assert len(deleted) == 5 - backup_db.MIN_KEEP
    assert remaining == sorted(names, reverse=True)[: backup_db.MIN_KEEP]


def test_prune_keeps_fresh_files(tmp_path):
    db = str(tmp_path / "t.db")
    bdir = str(tmp_path / "backups")
    _make_db(db, "v1")
    for _ in range(2):
        backup_db.create_backup("daily", db_path=db, backup_dir=bdir)
    assert backup_db.prune(bdir) == []
    assert len(backup_db.list_backups(bdir)) == 2


# ── Clone prod → dev ─────────────────────────────────────────────────────────

def test_clone_prod_to_dev_copies_data(tmp_path):
    prod = str(tmp_path / "prod.db")
    dev = str(tmp_path / "dev.db")
    bdir = str(tmp_path / "backups")
    _make_db(prod, "prod-data")
    _make_db(dev, "dev-data")

    safety = backup_db.clone_prod_to_dev(
        prod_db_path=prod, dev_db_path=dev, backup_dir=bdir, run_migrations=False
    )
    assert _read_marker(dev) == "prod-data"   # dev overwritten with prod data
    assert _read_marker(prod) == "prod-data"  # prod is read-only, untouched
    assert "pre-restore" in safety            # dev safety backup was taken

    # The safety backup preserves the pre-copy dev state
    raw = str(tmp_path / "old_dev.db")
    with gzip.open(os.path.join(bdir, safety), "rb") as f_in, open(raw, "wb") as f_out:
        f_out.write(f_in.read())
    assert _read_marker(raw) == "dev-data"


def test_clone_missing_prod_raises(tmp_path):
    dev = str(tmp_path / "dev.db")
    _make_db(dev, "dev-data")
    with pytest.raises(FileNotFoundError):
        backup_db.clone_prod_to_dev(
            prod_db_path=str(tmp_path / "nope.db"), dev_db_path=dev,
            backup_dir=str(tmp_path / "b"), run_migrations=False,
        )
    assert _read_marker(dev) == "dev-data"  # dev untouched on failure


def test_clone_missing_dev_raises(tmp_path):
    prod = str(tmp_path / "prod.db")
    _make_db(prod, "prod-data")
    with pytest.raises(FileNotFoundError):
        backup_db.clone_prod_to_dev(
            prod_db_path=prod, dev_db_path=str(tmp_path / "nope.db"),
            backup_dir=str(tmp_path / "b"), run_migrations=False,
        )


# ── Admin routes ─────────────────────────────────────────────────────────────

@pytest.fixture()
def backups_in_tmp(tmp_path, monkeypatch):
    """Point the engine's default backup dir at a temp location."""
    import paths
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    return str(tmp_path / "backups")


def test_db_page_requires_login(flask_app):
    anon = flask_app.test_client()
    rv = anon.get("/admin/db")
    assert rv.status_code == 302
    assert "/auth/login" in rv.headers["Location"]


def test_db_page_renders_for_admin(client, backups_in_tmp):
    rv = client.get("/admin/db")
    assert rv.status_code == 200
    assert "Backup acum".encode("utf-8") in rv.data


def test_db_page_shows_clone_button(client, backups_in_tmp):
    rv = client.get("/admin/db")
    assert rv.status_code == 200
    assert "/admin/db/clone-prod".encode("utf-8") in rv.data
    assert "PRD".encode("utf-8") in rv.data


def test_manual_backup_route(client, backups_in_tmp):
    rv = client.post("/admin/db/backup", follow_redirects=True)
    assert rv.status_code == 200
    backups = backup_db.list_backups(backups_in_tmp)
    assert len(backups) == 1
    assert backups[0]["tag"] == "manual"


def test_restore_route_requires_exact_confirmation(client, backups_in_tmp, db_path):
    client.post("/admin/db/backup")
    name = backup_db.list_backups(backups_in_tmp)[0]["name"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET email='changed@test.local' WHERE username='testadmin'")
    conn.commit()
    conn.close()

    rv = client.post("/admin/db/restore", data={"name": name, "confirm": "yes"},
                     follow_redirects=True)
    assert rv.status_code == 200
    conn = sqlite3.connect(db_path)
    email = conn.execute(
        "SELECT email FROM users WHERE username='testadmin'"
    ).fetchone()[0]
    conn.close()
    assert email == "changed@test.local"  # nothing restored


def test_restore_route_round_trip(client, backups_in_tmp, db_path):
    # Known starting state (independent of test ordering)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET email='test@test.local' WHERE username='testadmin'")
    conn.commit()
    conn.close()

    client.post("/admin/db/backup")
    name = backup_db.list_backups(backups_in_tmp)[0]["name"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET email='changed2@test.local' WHERE username='testadmin'")
    conn.commit()
    conn.close()

    rv = client.post("/admin/db/restore", data={"name": name, "confirm": "RESTORE"},
                     follow_redirects=True)
    assert rv.status_code == 200

    conn = sqlite3.connect(db_path)
    email = conn.execute(
        "SELECT email FROM users WHERE username='testadmin'"
    ).fetchone()[0]
    conn.close()
    assert email == "test@test.local"  # restored to pre-change state

    tags = [b["tag"] for b in backup_db.list_backups(backups_in_tmp)]
    assert "pre-restore" in tags  # safety backup of the overwritten state

    # Audit log captured the restore
    conn = sqlite3.connect(db_path)
    n = conn.execute(
        "SELECT COUNT(*) FROM auth_log WHERE event='db_restore'"
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_clone_route_requires_exact_confirmation(client, backups_in_tmp):
    rv = client.post("/admin/db/clone-prod", data={"confirm": "yes"},
                     follow_redirects=True)
    assert rv.status_code == 200
    tags = [b["tag"] for b in backup_db.list_backups(backups_in_tmp)]
    assert "pre-restore" not in tags  # nothing happened — no safety backup taken


def test_clone_route_success(client, backups_in_tmp, db_path):
    rv = client.post("/admin/db/clone-prod", data={"confirm": "COPY"},
                     follow_redirects=True)
    assert rv.status_code == 200
    tags = [b["tag"] for b in backup_db.list_backups(backups_in_tmp)]
    assert "pre-restore" in tags  # dev safety backup of the overwritten state

    conn = sqlite3.connect(db_path)
    n = conn.execute(
        "SELECT COUNT(*) FROM auth_log WHERE event='db_clone_prod'"
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_download_rejects_unknown_backup(client, backups_in_tmp):
    rv = client.get("/admin/db/download/torb_2026-01-01_000000_manual.db.gz")
    assert rv.status_code == 302  # redirect with flash, not a file


def test_download_serves_backup(client, backups_in_tmp):
    client.post("/admin/db/backup")
    name = backup_db.list_backups(backups_in_tmp)[0]["name"]
    rv = client.get(f"/admin/db/download/{name}")
    assert rv.status_code == 200
    assert rv.data[:2] == b"\x1f\x8b"  # gzip magic
