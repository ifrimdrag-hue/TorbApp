"""Rotating JSON log for eMAG API requests — keeps the last MAX_ENTRIES records."""

import json
import time
from contextlib import contextmanager
# from datetime import datetime  # JSON request logging disabled
from pathlib import Path

_LOG_FILE = Path(__file__).resolve().parents[3] / "logs" / "emag_req.json"
MAX_ENTRIES = 20


def _read() -> list:
    try:
        return json.loads(_LOG_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write(entries: list) -> None:
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LOG_FILE.write_text(
        json.dumps(entries[-MAX_ENTRIES:], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _parse_body(text: str):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


def append(
    *,
    url: str,
    payload,
    status_code: int | None = None,
    response_text: str | None = None,
    duration_ms: float | None = None,
    error: str | None = None,
) -> None:
    # JSON request logging disabled — uncomment below (and the datetime import)
    # to re-enable writing logs/emag_req.json.
    # response = _parse_body(response_text) if response_text is not None else None
    # entry = {
    #     "timestamp": datetime.now().isoformat(timespec="seconds"),
    #     "url": url,
    #     "payload": payload,
    #     "status_code": status_code,
    #     "response": response,
    #     "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
    #     "error": error,
    # }
    # entries = _read()
    # entries.append(entry)
    # _write(entries)
    return None


@contextmanager
def capture(*, url: str, payload):
    """Context manager that times the block and appends the result automatically.

    Usage::

        with capture(url=url, payload=batch) as ctx:
            resp = await client.post(url, json=batch)
            ctx.status_code = resp.status_code
            ctx.response_text = resp.text
    """
    class _Ctx:
        status_code: int | None = None
        response_text: str | None = None

    ctx = _Ctx()
    t0 = time.perf_counter()
    try:
        yield ctx
    except Exception as exc:
        append(
            url=url,
            payload=payload,
            status_code=ctx.status_code,
            response_text=ctx.response_text,
            duration_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )
        raise
    else:
        append(
            url=url,
            payload=payload,
            status_code=ctx.status_code,
            response_text=ctx.response_text,
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
