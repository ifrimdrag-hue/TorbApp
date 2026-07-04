import logging
import logging.handlers
import os

import pytest

import logging_config


@pytest.fixture
def clean_root():
    """Isolate the global root logger so each test starts and ends clean."""
    root = logging.root
    saved_handlers = root.handlers[:]
    saved_level = root.level
    had_marker = hasattr(root, logging_config._MARKER)
    root.handlers = []
    if had_marker:
        delattr(root, logging_config._MARKER)
    yield root
    for h in root.handlers:
        h.close()
    root.handlers = saved_handlers
    root.level = saved_level
    if hasattr(root, logging_config._MARKER):
        delattr(root, logging_config._MARKER)
    if had_marker:
        setattr(root, logging_config._MARKER, True)


def _rotating(root):
    return [h for h in root.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)]


def test_attaches_app_and_error_handlers(clean_root, tmp_path):
    logging_config.setup_logging(log_dir=str(tmp_path))
    names = {os.path.basename(h.baseFilename) for h in _rotating(clean_root)}
    assert {"app.log", "errors.log"} <= names


def test_error_handler_is_error_level(clean_root, tmp_path):
    logging_config.setup_logging(log_dir=str(tmp_path))
    err = next(h for h in _rotating(clean_root)
               if os.path.basename(h.baseFilename) == "errors.log")
    assert err.level == logging.ERROR


def test_noisy_loggers_quieted(clean_root, tmp_path):
    logging_config.setup_logging(log_dir=str(tmp_path))
    for name in ("werkzeug", "httpx", "urllib3"):
        assert logging.getLogger(name).level == logging.WARNING


def test_idempotent_no_duplicate_handlers(clean_root, tmp_path):
    logging_config.setup_logging(log_dir=str(tmp_path))
    logging_config.setup_logging(log_dir=str(tmp_path))
    assert len(_rotating(clean_root)) == 2


def test_respects_log_level_env(clean_root, tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    logging_config.setup_logging(log_dir=str(tmp_path))
    assert clean_root.level == logging.WARNING
