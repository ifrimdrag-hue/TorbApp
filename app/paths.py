"""Centralized path resolution — works both in dev and PyInstaller frozen mode."""
import sys
import os


def _base():
    if getattr(sys, 'frozen', False):
        # Running as packaged .exe — install dir is next to the executable
        return os.path.dirname(sys.executable)
    # Dev mode — two levels up from app/paths.py → project root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = _base()
DATA_DIR = os.path.join(BASE_DIR, 'data')
DOCS_DIR = os.path.join(BASE_DIR, 'docs_input')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
DB_PATH  = os.path.join(DATA_DIR, 'torb.db')
