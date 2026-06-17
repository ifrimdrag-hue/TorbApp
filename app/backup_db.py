"""SQLite online backup/restore engine for data/torb.db.

Used by the CLI wrapper (etl/backup_db.py — cron + CI) and the admin UI
(blueprints/admin_db.py). Stdlib only, so it runs before pip install in CI.

Backups are gzipped snapshots taken with the SQLite online backup API —
safe while the app is running under WAL (a plain file copy is not).
Naming: torb_YYYY-MM-DD_HHMMSS_<tag>.db.gz in data/backups/.
"""
import gzip
import os
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime

RETENTION_DAYS = 15
MIN_KEEP = 3            # never prune below this many, regardless of age
VALID_TAGS = ('daily', 'pre-deploy', 'pre-restore', 'manual')
_NAME_RE = re.compile(
    r'^torb_\d{4}-\d{2}-\d{2}_\d{6}(?:-\d+)?_(?P<tag>'
    + '|'.join(VALID_TAGS) + r')\.db\.gz$'
)


def _db_path():
    import paths
    return paths.DB_PATH


def _backup_dir():
    import paths
    return os.path.join(paths.DATA_DIR, 'backups')


def _snapshot_to(db_path: str, dest_path: str) -> None:
    """Consistent snapshot of a (possibly live) DB via the online backup API."""
    src = sqlite3.connect(db_path)
    dest = sqlite3.connect(dest_path)
    try:
        # Chunked copy: writers are only blocked per-chunk, not for the whole copy
        src.backup(dest, pages=8192, sleep=0.1)
    finally:
        dest.close()
        src.close()


def create_backup(tag: str = 'manual', db_path: str = None, backup_dir: str = None) -> str:
    """Snapshot db_path into backup_dir, gzipped. Returns the backup file path."""
    if tag not in VALID_TAGS:
        raise ValueError(f'invalid tag {tag!r}, expected one of {VALID_TAGS}')
    db_path = db_path or _db_path()
    backup_dir = backup_dir or _backup_dir()
    os.makedirs(backup_dir, exist_ok=True)

    stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    final = os.path.join(backup_dir, f'torb_{stamp}_{tag}.db.gz')
    seq = 1
    while os.path.exists(final):  # same-second collision: add a sequence suffix
        seq += 1
        final = os.path.join(backup_dir, f'torb_{stamp}-{seq}_{tag}.db.gz')
    tmp_db = final + '.snapshot.tmp'
    tmp_gz = final + '.tmp'
    try:
        _snapshot_to(db_path, tmp_db)
        with open(tmp_db, 'rb') as f_in, gzip.open(tmp_gz, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out, length=1024 * 1024)
        os.replace(tmp_gz, final)
    finally:
        for p in (tmp_db, tmp_gz):
            if os.path.exists(p):
                os.unlink(p)
    return final


def list_backups(backup_dir: str = None) -> list:
    """Backups newest-first: [{name, tag, size, created_at}]."""
    backup_dir = backup_dir or _backup_dir()
    if not os.path.isdir(backup_dir):
        return []
    out = []
    for name in os.listdir(backup_dir):
        m = _NAME_RE.match(name)
        if not m:
            continue
        full = os.path.join(backup_dir, name)
        out.append({
            'name': name,
            'tag': m.group('tag'),
            'size': os.path.getsize(full),
            'created_at': datetime.fromtimestamp(os.path.getmtime(full)),
        })
    out.sort(key=lambda b: b['name'], reverse=True)
    return out


def prune(backup_dir: str = None, retention_days: int = RETENTION_DAYS) -> list:
    """Delete backups older than retention_days, always keeping the newest
    MIN_KEEP. Returns the deleted file names."""
    backup_dir = backup_dir or _backup_dir()
    backups = list_backups(backup_dir)  # newest-first
    cutoff = time.time() - retention_days * 86400
    deleted = []
    for b in backups[MIN_KEEP:]:
        full = os.path.join(backup_dir, b['name'])
        if os.path.getmtime(full) < cutoff:
            os.unlink(full)
            deleted.append(b['name'])
    return deleted


def _run_migrations(db_path: str) -> None:
    # Project root on sys.path so the migrations package resolves from any CWD
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from migrations.runner import run_all
    run_all(db_path)


def _prod_db_path():
    import paths
    return os.environ.get('PROD_DB_PATH') or paths.DB_PATH


def _dev_db_path():
    import paths
    return os.environ.get('DEV_DB_PATH') or paths.DB_PATH


def clone_prod_to_dev(prod_db_path: str = None, dev_db_path: str = None,
                      backup_dir: str = None, run_migrations: bool = True) -> str:
    """Overwrite the dev DB with a live snapshot of the prod DB.

    Direction is fixed: prod is a read-only source, dev is the target — so this
    is safe to trigger from either environment (prod is never written). Safety
    order: validate paths → snapshot prod → integrity_check → pre-restore backup
    of the current dev DB → copy into dev → re-apply migrations (prod schema may
    differ). Returns the name of the pre-copy safety backup.
    """
    prod_db_path = prod_db_path or _prod_db_path()
    dev_db_path = dev_db_path or _dev_db_path()
    backup_dir = backup_dir or _backup_dir()
    if not os.path.isfile(prod_db_path):
        raise FileNotFoundError(prod_db_path)
    if not os.path.isfile(dev_db_path):
        raise FileNotFoundError(dev_db_path)
    os.makedirs(backup_dir, exist_ok=True)

    tmp_db = os.path.join(backup_dir, 'clone-prod.tmp')
    try:
        _snapshot_to(prod_db_path, tmp_db)

        check = sqlite3.connect(tmp_db)
        try:
            result = check.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            check.close()
        if result != 'ok':
            raise RuntimeError(f'prod snapshot failed integrity check: {result}')

        safety = create_backup('pre-restore', db_path=dev_db_path, backup_dir=backup_dir)
        _snapshot_to(tmp_db, dev_db_path)
    finally:
        if os.path.exists(tmp_db):
            os.unlink(tmp_db)

    if run_migrations:
        _run_migrations(dev_db_path)
    return os.path.basename(safety)


def restore_backup(name: str, db_path: str = None, backup_dir: str = None,
                   run_migrations: bool = True) -> str:
    """Restore the named backup over the live DB.

    Safety order: validate name → gunzip to temp → integrity_check →
    pre-restore backup of the current DB → copy into the live DB via the
    backup API → re-apply migrations (the backup may predate current schema).
    Returns the name of the pre-restore safety backup.
    """
    if not _NAME_RE.match(name):
        raise ValueError(f'invalid backup name: {name!r}')
    db_path = db_path or _db_path()
    backup_dir = backup_dir or _backup_dir()
    source = os.path.join(backup_dir, name)
    if not os.path.isfile(source):
        raise FileNotFoundError(source)

    tmp_db = source + '.restore.tmp'
    try:
        with gzip.open(source, 'rb') as f_in, open(tmp_db, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out, length=1024 * 1024)

        check = sqlite3.connect(tmp_db)
        try:
            result = check.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            check.close()
        if result != 'ok':
            raise RuntimeError(f'backup failed integrity check: {result}')

        safety = create_backup('pre-restore', db_path=db_path, backup_dir=backup_dir)
        _snapshot_to(tmp_db, db_path)
    finally:
        if os.path.exists(tmp_db):
            os.unlink(tmp_db)

    if run_migrations:
        _run_migrations(db_path)
    return os.path.basename(safety)
