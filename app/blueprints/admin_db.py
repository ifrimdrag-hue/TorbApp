# app/blueprints/admin_db.py
"""DB maintenance admin pages (backup list, manual backup, guarded restore).

Routes are registered on the existing admin_bp (mounted at /admin) so the
sidebar highlight and role gating behave like the user-management pages.
Imported for its side effects in app.py before admin_bp is registered.
"""
import logging

from flask import flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user

from backup_db import _backup_dir, create_backup, list_backups, prune, restore_backup
from blueprints.auth import _log, admin_bp, require_role

_logger = logging.getLogger(__name__)

# POST routes rely on the app-wide CSRFProtect (csrf.init_app in app.py);
# the template includes csrf_token in every form.


@admin_bp.route("/db")
@require_role("admin")
def db_maintenance():
    return render_template("admin/db.html", backups=list_backups())


@admin_bp.route("/db/backup", methods=["POST"])
@require_role("admin")
def db_backup_now():
    try:
        path = create_backup("manual")
        prune()
        _log(current_user.id, "db_backup", request.remote_addr or "0.0.0.0", path)
        flash("Backup creat cu succes.", "success")
    except Exception as exc:
        _logger.exception("Manual backup failed")
        flash(f"Backup eșuat: {exc}", "danger")
    return redirect(url_for("admin.db_maintenance"))


@admin_bp.route("/db/restore", methods=["POST"])
@require_role("admin")
def db_restore():
    name = request.form.get("name", "")
    confirm = request.form.get("confirm", "")
    if confirm.strip() != "RESTORE":
        flash("Restaurare anulată — confirmarea trebuie să fie exact RESTORE.", "warning")
        return redirect(url_for("admin.db_maintenance"))
    try:
        safety = restore_backup(name)
        _clear_query_caches()
        _log(current_user.id, "db_restore", request.remote_addr or "0.0.0.0",
             f"{name} (safety: {safety})")
        flash(
            f"Baza de date a fost restaurată din {name}. "
            f"Backup de siguranță pre-restaurare: {safety}. "
            "Recomandat: reporniți serviciul pentru consistența completă a cache-urilor.",
            "success",
        )
    except Exception as exc:
        _logger.exception("Restore failed for %s", name)
        flash(f"Restaurare eșuată: {exc}", "danger")
    return redirect(url_for("admin.db_maintenance"))


@admin_bp.route("/db/download/<name>")
@require_role("admin")
def db_download(name):
    # restore_backup-style name validation happens in send_from_directory via
    # safe path joining, but reject anything not produced by the engine anyway
    if not any(b["name"] == name for b in list_backups()):
        flash("Backup inexistent.", "warning")
        return redirect(url_for("admin.db_maintenance"))
    return send_from_directory(_backup_dir(), name, as_attachment=True)


def _clear_query_caches():
    """In-process caches of THIS worker; other gunicorn workers keep theirs
    until restart (hence the restart recommendation in the flash message)."""
    from queries._shared import (
        _agents_list_cached,
        _brands_list_cached,
        max_luna_for_year,
        rebuild_cond_resolved,
    )
    max_luna_for_year.cache_clear()
    _agents_list_cached.cache_clear()
    _brands_list_cached.cache_clear()
    rebuild_cond_resolved()
