"""Persistenta pentru postari automate.

Fisier: data/auto_posts.json
Schema:
{
  "pending": { ... } | null,        # postarea curenta in asteptarea aprobarii
  "history": [ ... ],               # postari aprobate sau respinse
  "settings": {
    "scheduler_enabled": bool,
    "interval_hours": int,
    "last_auto_run": "ISO" | null,
    "last_empty_pool_notice": "ISO" | null
  }
}

Pending item:
{
  "id": "uuid",
  "photo_filename": "foo.jpg",
  "image_analysis": "...",
  "caption": "...",
  "hashtags": ["#a", "#b", ...],
  "alt_text": "...",
  "warnings": [...],
  "brand_detected": "Basilur" | null,
  "created_at": "ISO",
  "regen_count": 0,
  "trigger": "manual" | "auto"
}
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
FILE = DATA_DIR / "auto_posts.json"

DEFAULT_STATE: dict[str, Any] = {
    "pending": None,
    "history": [],
    "settings": {
        "scheduler_enabled": False,
        "interval_hours": 48,
        "last_auto_run": None,
        "last_empty_pool_notice": None,
    },
}


def _load() -> dict[str, Any]:
    if not FILE.exists():
        return json.loads(json.dumps(DEFAULT_STATE))
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(json.dumps(DEFAULT_STATE))
    # ensure keys exist
    for k, v in DEFAULT_STATE.items():
        if k not in data:
            data[k] = v
    for k, v in DEFAULT_STATE["settings"].items():
        if k not in data["settings"]:
            data["settings"][k] = v
    return data


def _save(state: dict[str, Any]) -> None:
    FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def get_state() -> dict[str, Any]:
    return _load()


def get_pending() -> dict | None:
    return _load().get("pending")


def set_pending(item: dict) -> dict:
    state = _load()
    state["pending"] = item
    _save(state)
    return item


def clear_pending() -> None:
    state = _load()
    state["pending"] = None
    _save(state)


def update_pending(updates: dict) -> dict | None:
    state = _load()
    if not state.get("pending"):
        return None
    state["pending"].update(updates)
    _save(state)
    return state["pending"]


def archive_pending(action: str) -> dict | None:
    """Muta pending-ul in history cu actiunea ('approved' | 'rejected')."""
    state = _load()
    pending = state.get("pending")
    if not pending:
        return None
    pending["action"] = action
    pending["resolved_at"] = datetime.now().isoformat()
    state["history"].insert(0, pending)
    state["history"] = state["history"][:200]  # cap la 200
    state["pending"] = None
    _save(state)
    return pending


def get_history(limit: int = 50) -> list[dict]:
    return _load().get("history", [])[:limit]


def get_settings() -> dict:
    return _load().get("settings", {})


def update_settings(updates: dict) -> dict:
    state = _load()
    state["settings"].update(updates)
    _save(state)
    return state["settings"]


def new_pending_id() -> str:
    return str(uuid.uuid4())
