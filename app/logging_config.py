"""Central logging configuration for the Torb app.

Single responsibility: attach rotating file handlers (app.log + errors.log)
to the root logger, quiet noisy third-party loggers, and echo to the console
only in debug mode. Safe to call more than once (idempotent).
"""

import logging
import logging.handlers
import os

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MARKER = "_torb_logging_configured"
_NOISY = {
    "werkzeug": logging.WARNING,
    "httpx": logging.WARNING,
    "urllib3": logging.WARNING,
}


def _default_log_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
    )


def setup_logging(log_dir: str | None = None, level: str | None = None) -> None:
    root = logging.root

    # Quiet noisy third-party loggers on every call (cheap, idempotent).
    for name, lvl in _NOISY.items():
        logging.getLogger(name).setLevel(lvl)

    level_name = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    if getattr(root, _MARKER, False):
        return

    log_dir = log_dir or _default_log_dir()
    os.makedirs(log_dir, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)

    app_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    app_handler.setFormatter(formatter)
    root.addHandler(app_handler)

    error_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "errors.log"),
        maxBytes=1 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    root.addHandler(error_handler)

    if os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes"):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)

    setattr(root, _MARKER, True)
