"""
Versioned migration runner for torb.db.

Migration files live alongside this module.
Naming convention: NNNN_YYYYMMDD_description.py
  e.g. 0001_20260523_initial.py

Each file must export:
    VERSION: int   — the NNNN prefix as an integer
    NAME:    str   — human-readable label (used in schema_version table)
    up(conn)       — receives an open sqlite3.Connection; must NOT call conn.commit()
                     (the runner commits after recording the version)

CLI usage (from project root):
    python migrations/runner.py                  # resolves DB_PATH from app/paths.py
    python migrations/runner.py data/torb.db     # explicit path
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).parent


def _ensure_schema_version(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER PRIMARY KEY,
            name        TEXT    NOT NULL,
            applied_at  DATETIME DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"_migration_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_all(db_path: str) -> None:
    """Apply every pending migration in NNNN order to the database at db_path."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    _ensure_schema_version(conn)

    applied = {r[0] for r in conn.execute("SELECT version FROM schema_version").fetchall()}

    files = sorted(
        _HERE.glob("[0-9][0-9][0-9][0-9]_*.py"),
        key=lambda p: int(p.name.split("_")[0]),
    )
    pending = [p for p in files if int(p.name.split("_")[0]) not in applied]

    if not pending:
        print("DB schema is up to date.", flush=True)
        conn.close()
        return

    for path in pending:
        version = int(path.name.split("_")[0])
        name = path.stem
        print(f"  Applying {version:04d}: {name} ...", flush=True)
        try:
            mod = _load(path)
            mod.up(conn)
            conn.execute(
                "INSERT INTO schema_version (version, name) VALUES (?, ?)",
                (version, name),
            )
            conn.commit()
            print(f"  {version:04d} OK.", flush=True)
        except Exception as exc:
            conn.rollback()
            conn.close()
            raise RuntimeError(f"Migration {version:04d} failed: {exc}") from exc

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _db_path = sys.argv[1]
    else:
        _root = Path(__file__).parent.parent
        sys.path.insert(0, str(_root / "app"))
        from paths import DB_PATH  # noqa: E402
        _db_path = DB_PATH

    print(f"Running migrations on: {_db_path}", flush=True)
    run_all(_db_path)
    print("Done.", flush=True)
