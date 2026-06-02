"""Scheduler pentru postari automate — rulat ca daemon thread Flask-compatible."""

import logging
import threading
import time
from datetime import datetime, timedelta

from . import pool, storage
from .generator import generate_auto_post


log = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 10 * 60  # 10 minute


def _now() -> datetime:
    return datetime.now()


def _should_run_now(sett: dict) -> bool:
    if not sett.get("scheduler_enabled"):
        return False
    last = sett.get("last_auto_run")
    interval_h = sett.get("interval_hours", 48)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    return _now() - last_dt >= timedelta(hours=interval_h)


def _generate_one(trigger: str) -> dict | None:
    photo = pool.pick_random()
    if not photo:
        return None
    img_bytes = pool.read_bytes(photo)
    media_type = pool.media_type_for(photo)
    result = generate_auto_post(img_bytes, media_type)
    if not result.get("ok"):
        log.error("auto-post generation failed: %s", result.get("error"))
        return None
    data = result["data"]
    pending = {
        "id": storage.new_pending_id(),
        "photo_filename": photo,
        "image_analysis": data.get("image_analysis", ""),
        "caption": data.get("caption", ""),
        "hashtags": data.get("hashtags", []),
        "alt_text": data.get("alt_text", ""),
        "brand_detected": data.get("brand_detected"),
        "warnings": data.get("warnings", []),
        "created_at": _now().isoformat(),
        "regen_count": 0,
        "trigger": trigger,
    }
    storage.set_pending(pending)
    return pending


def trigger_manual() -> dict:
    if storage.get_pending():
        return {"ok": False, "error": "Exista deja o postare in asteptare. Rezolv-o intai (Aproba/Respinge)."}
    pending = _generate_one(trigger="manual")
    if pending is None:
        if pool.count_available() == 0:
            return {"ok": False, "error": "Pool-ul de poze e gol. Incarca poze inainte sa generezi."}
        return {"ok": False, "error": "Generarea AI a esuat. Incearca din nou sau verifica logs."}
    return {"ok": True, "pending": pending}


def _scheduler_loop() -> None:
    log.info("auto-posts scheduler started")
    while True:
        try:
            sett = storage.get_settings()
            if _should_run_now(sett) and not storage.get_pending():
                if pool.count_available() == 0:
                    storage.update_settings({"last_empty_pool_notice": _now().isoformat()})
                    log.info("auto-posts: pool empty, skipping")
                else:
                    log.info("auto-posts: triggering scheduled generation")
                    pending = _generate_one(trigger="auto")
                    if pending:
                        storage.update_settings({"last_auto_run": _now().isoformat()})
        except Exception:
            log.exception("auto-posts scheduler tick failed")
        time.sleep(CHECK_INTERVAL_SECONDS)


_thread: threading.Thread | None = None


def start_background_scheduler() -> None:
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(
            target=_scheduler_loop,
            daemon=True,
            name="auto-posts-scheduler",
        )
        _thread.start()
