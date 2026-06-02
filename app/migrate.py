# app/migrate.py
import os
import sys

# Make the project root importable so `migrations` package is resolvable
# regardless of the working directory when the Flask app starts.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from migrations.runner import run_all  # noqa: E402
from paths import DB_PATH  # noqa: E402


def apply_migrations():
    run_all(DB_PATH)
