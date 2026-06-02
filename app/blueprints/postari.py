import logging
import zipfile
from datetime import datetime
from io import BytesIO

from flask import Blueprint, jsonify, render_template, request, send_file

from automations.campanii.storage import get as get_campanie, load_all as load_campanii


postari_bp = Blueprint("postari", __name__)
log = logging.getLogger(__name__)


# ── Pages ───────────────────────────────────────────────────────────────────

@postari_bp.route("/postari/instagram")
def instagram():
    campaigns = [c.model_dump(mode="json") for c in load_campanii()]
    active = [c for c in campaigns if c.get("status") in ("active", "planned")]
    return render_template("postari/instagram.html", campaigns=active)


@postari_bp.route("/postari/facebook")
def facebook():
    campaigns = [c.model_dump(mode="json") for c in load_campanii()]
    active = [c for c in campaigns if c.get("status") in ("active", "planned")]
    return render_template("postari/facebook.html", campaigns=active)


@postari_bp.route("/postari/auto")
def auto_posts_page():
    return render_template("postari/auto.html")


# ── Postari Instagram / Facebook ────────────────────────────────────────────

@postari_bp.route("/api/postari/ai-generate", methods=["POST"])
def postari_ai_generate():
    photo = request.files.get("photo")
    platform = request.form.get("platform", "")
    brand = request.form.get("brand", "") or None
    tone = request.form.get("tone", "") or None
    notes = request.form.get("notes", "")
    linked_campaign_id = request.form.get("linked_campaign_id", "")

    if platform not in ("instagram", "facebook"):
        return jsonify({"ok": False, "error": "Platforma trebuie sa fie 'instagram' sau 'facebook'"}), 400

    if not photo or not photo.filename:
        return jsonify({"ok": False, "error": "Trebuie o poza pentru generare"}), 400

    fname = photo.filename.lower()
    if fname.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif fname.endswith(".png"):
        media_type = "image/png"
    elif fname.endswith(".webp"):
        media_type = "image/webp"
    elif fname.endswith(".gif"):
        media_type = "image/gif"
    else:
        return jsonify({"ok": False, "error": "Format acceptat: .jpg, .png, .webp, .gif"}), 400

    image_bytes = photo.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        return jsonify({"ok": False, "error": "Imaginea e prea mare (max 10MB)"}), 400

    linked_campaign = None
    if linked_campaign_id:
        c = get_campanie(linked_campaign_id)
        if c:
            linked_campaign = c.model_dump(mode="json")

    from automations.ai.post_generator import generate_post_content
    result = generate_post_content(
        image_bytes=image_bytes,
        image_media_type=media_type,
        platform=platform,
        brand=brand,
        tone=tone,
        notes=notes,
        linked_campaign=linked_campaign,
    )
    return jsonify(result)


# ── Auto-posts ───────────────────────────────────────────────────────────────

@postari_bp.route("/api/auto-posts/state")
def auto_posts_state():
    from automations.auto_posts import pool as auto_pool, storage as auto_storage
    return jsonify({
        "pending": auto_storage.get_pending(),
        "settings": auto_storage.get_settings(),
        "pool_count": auto_pool.count_available(),
        "pool_files": auto_pool.list_available()[:50],
        "history": auto_storage.get_history(20),
    })


@postari_bp.route("/api/auto-posts/upload", methods=["POST"])
def auto_posts_upload():
    from automations.auto_posts import pool as auto_pool
    files = request.files.getlist("files")
    if not files:
        return jsonify({"ok": False, "error": "Nicio poza nu a fost incarcata."}), 400
    saved, errors = [], []
    for f in files:
        try:
            data = f.read()
            if not data:
                errors.append(f"{f.filename}: fisier gol")
                continue
            if len(data) > 15 * 1024 * 1024:
                errors.append(f"{f.filename}: prea mare (max 15MB)")
                continue
            name = auto_pool.save_upload(f.filename or "untitled.jpg", data)
            saved.append(name)
        except Exception as e:
            errors.append(f"{f.filename}: {e}")
    return jsonify({"ok": True, "saved": saved, "errors": errors,
                    "pool_count": auto_pool.count_available()})


@postari_bp.route("/api/auto-posts/generate", methods=["POST"])
def auto_posts_generate():
    from automations.auto_posts.scheduler import trigger_manual
    return jsonify(trigger_manual())


@postari_bp.route("/api/auto-posts/regenerate", methods=["POST"])
def auto_posts_regenerate():
    from automations.auto_posts import pool as auto_pool, storage as auto_storage
    from automations.auto_posts.generator import generate_auto_post
    payload = request.get_json(silent=True) or {}
    pending = auto_storage.get_pending()
    if not pending:
        return jsonify({"ok": False, "error": "Nu exista postare in asteptare."}), 400

    feedback = payload.get("feedback", "").strip()
    photo = pending["photo_filename"]
    img_bytes = auto_pool.read_bytes(photo)
    media_type = auto_pool.media_type_for(photo)

    result = generate_auto_post(img_bytes, media_type,
                                regen_feedback=feedback,
                                previous_caption=pending.get("caption", ""))
    if not result.get("ok"):
        return jsonify({"ok": False, "error": result.get("error", "Generare esuata.")}), 500

    data = result["data"]
    updated = auto_storage.update_pending({
        "caption": data.get("caption", ""),
        "hashtags": data.get("hashtags", []),
        "alt_text": data.get("alt_text", ""),
        "image_analysis": data.get("image_analysis", ""),
        "brand_detected": data.get("brand_detected"),
        "warnings": data.get("warnings", []),
        "regen_count": pending.get("regen_count", 0) + 1,
    })
    return jsonify({"ok": True, "pending": updated})


@postari_bp.route("/api/auto-posts/approve", methods=["POST"])
def auto_posts_approve():
    from automations.auto_posts import pool as auto_pool, storage as auto_storage
    pending = auto_storage.get_pending()
    if not pending:
        return jsonify({"ok": False, "error": "Nu exista postare in asteptare."}), 400

    photo = pending["photo_filename"]
    try:
        img_bytes = auto_pool.read_bytes(photo)
    except FileNotFoundError:
        return jsonify({"ok": False, "error": f"Poza nu mai exista in pool: {photo}"}), 404

    caption = pending.get("caption", "").strip()
    hashtags = pending.get("hashtags", [])
    alt_text = pending.get("alt_text", "")
    caption_full = caption + "\n\n" + " ".join(hashtags) if hashtags else caption
    caption_txt = (
        "=== CAPTION (copy-paste pe IG si FB) ===\n\n"
        f"{caption_full}\n\n"
        "=== ALT TEXT (pentru accesibilitate) ===\n\n"
        f"{alt_text}\n"
    )

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(photo, img_bytes)
        zf.writestr("caption.txt", caption_txt)

    try:
        auto_pool.move_to_used(photo)
    except FileNotFoundError:
        pass
    auto_storage.archive_pending("approved")

    zip_buf.seek(0)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    return send_file(zip_buf, mimetype="application/zip",
                     as_attachment=True, download_name=f"AutoPost_{ts}.zip")


@postari_bp.route("/api/auto-posts/reject", methods=["POST"])
def auto_posts_reject():
    from automations.auto_posts import storage as auto_storage
    pending = auto_storage.archive_pending("rejected")
    if not pending:
        return jsonify({"ok": False, "error": "Nu exista postare in asteptare."}), 400
    return jsonify({"ok": True})


@postari_bp.route("/api/auto-posts/settings", methods=["POST"])
def auto_posts_settings():
    from automations.auto_posts import storage as auto_storage
    payload = request.get_json(silent=True) or {}
    updates = {}
    if "scheduler_enabled" in payload:
        updates["scheduler_enabled"] = bool(payload["scheduler_enabled"])
    if "interval_hours" in payload:
        try:
            ih = int(payload["interval_hours"])
            if not (1 <= ih <= 720):
                raise ValueError
            updates["interval_hours"] = ih
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "interval_hours trebuie sa fie intre 1 si 720."}), 400
    if not updates:
        return jsonify({"ok": False, "error": "Nimic de actualizat."}), 400
    return jsonify({"ok": True, "settings": auto_storage.update_settings(updates)})


@postari_bp.route("/api/auto-posts/photo/<path:filename>")
def auto_posts_photo(filename):
    from automations.auto_posts import pool as auto_pool
    p = auto_pool.get_path(filename)
    if not p.exists():
        return jsonify({"error": "Poza nu exista."}), 404
    return send_file(str(p), mimetype=auto_pool.media_type_for(filename))
