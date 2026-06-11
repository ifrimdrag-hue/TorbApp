"""CLI for DB backup/restore. Run from project root (like all etl/ scripts).

    python etl/backup_db.py backup [--tag daily|pre-deploy|manual]
    python etl/backup_db.py list
    python etl/backup_db.py restore <backup-name>

Stdlib only — safe to run in CI before pip install. Scheduled daily on the
prod VPS via cron (see context/infrastructure.md).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'
))
from backup_db import create_backup, list_backups, prune, restore_backup  # noqa: E402


def _fmt_size(n: int) -> str:
    return f'{n / 1048576:.1f} MB'


def main() -> int:
    parser = argparse.ArgumentParser(description='torb.db backup/restore')
    sub = parser.add_subparsers(dest='command')

    p_backup = sub.add_parser('backup', help='create a backup and prune old ones')
    p_backup.add_argument('--tag', default='manual',
                          choices=['daily', 'pre-deploy', 'manual'])

    sub.add_parser('list', help='list available backups')

    p_restore = sub.add_parser('restore', help='restore a backup over the live DB')
    p_restore.add_argument('name', help='backup file name (see: list)')

    args = parser.parse_args()
    command = args.command or 'backup'

    if command == 'backup':
        tag = getattr(args, 'tag', 'manual')
        path = create_backup(tag)
        print(f'Backup created: {path} ({_fmt_size(os.path.getsize(path))})')
        deleted = prune()
        for name in deleted:
            print(f'Pruned: {name}')
        return 0

    if command == 'list':
        backups = list_backups()
        if not backups:
            print('No backups found.')
            return 0
        for b in backups:
            stamp = b['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            print(f"{b['name']}  {stamp}  {_fmt_size(b['size'])}")
        return 0

    if command == 'restore':
        safety = restore_backup(args.name)
        print(f'Restored {args.name} (pre-restore safety backup: {safety})')
        print('Restart the service for full cache consistency: sudo systemctl restart torb-py')
        return 0

    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
