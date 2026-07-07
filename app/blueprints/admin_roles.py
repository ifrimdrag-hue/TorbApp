"""Role management routes (create/edit-label/delete) on admin_bp.

Imported for side effects in app.py before admin_bp is registered.
"""
import sqlite3

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from paths import DB_PATH
from blueprints.auth import RoleForm, SLUG_RE, _log, admin_bp, require_role


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


@admin_bp.route("/roles/new", methods=["GET", "POST"])
@require_role("admin")
def role_new():
    form = RoleForm()
    if form.validate_on_submit():
        name = form.name.data.strip().lower()
        if not SLUG_RE.match(name):
            form.name.errors.append("Slug invalid: doar litere mici, cifre, underscore.")
        else:
            try:
                with _conn() as c:
                    c.execute(
                        "INSERT INTO adm_roles (name, label, is_system) VALUES (?,?,0)",
                        (name, form.label.data.strip()),
                    )
                _log(current_user.id, "role_created", request.remote_addr or "0.0.0.0", name)
                flash("Rol creat.", "success")
                return redirect(url_for("admin.users"))
            except sqlite3.IntegrityError:
                form.name.errors.append("Nume de rol deja existent.")
    return render_template("admin/role_form.html", form=form, title="Rol nou",
                           action=url_for("admin.role_new"))


@admin_bp.route("/roles/<int:rid>/edit", methods=["GET", "POST"])
@require_role("admin")
def role_edit(rid):
    with _conn() as c:
        row = c.execute("SELECT * FROM adm_roles WHERE id=?", (rid,)).fetchone()
    if not row:
        flash("Rol inexistent.", "warning")
        return redirect(url_for("admin.users"))
    form = RoleForm()
    if request.method == "GET":
        form.name.data = row["name"]
        form.label.data = row["label"]
    if form.validate_on_submit():
        # name (slug) is immutable after creation — only label changes
        with _conn() as c:
            c.execute("UPDATE adm_roles SET label=? WHERE id=?",
                      (form.label.data.strip(), rid))
        _log(current_user.id, "role_edited", request.remote_addr or "0.0.0.0", row["name"])
        flash("Rol actualizat.", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/role_form.html", form=form,
                           title="Editare rol", action=url_for("admin.role_edit", rid=rid),
                           name_locked=True)


@admin_bp.route("/roles/<int:rid>/delete", methods=["POST"])
@require_role("admin")
def role_delete(rid):
    from flask import current_app
    from flask_wtf.csrf import validate_csrf
    if current_app.config.get("WTF_CSRF_ENABLED", True):
        try:
            validate_csrf(request.form.get("csrf_token"))
        except Exception:
            from flask import abort
            abort(403)
    with _conn() as c:
        row = c.execute("SELECT name, is_system FROM adm_roles WHERE id=?", (rid,)).fetchone()
        if not row:
            flash("Rol inexistent.", "warning")
            return redirect(url_for("admin.users"))
        if row["is_system"]:
            flash("Rolurile de sistem nu pot fi șterse.", "warning")
            return redirect(url_for("admin.users"))
        in_use = c.execute("SELECT COUNT(*) FROM adm_users WHERE role=?", (row["name"],)).fetchone()[0]
        if in_use:
            flash(f"Rolul este atribuit la {in_use} utilizator(i). Reatribuiți-i întâi.", "warning")
            return redirect(url_for("admin.users"))
        c.execute("DELETE FROM adm_role_nav WHERE role_id=?", (rid,))
        c.execute("DELETE FROM adm_roles WHERE id=?", (rid,))
    _log(current_user.id, "role_deleted", request.remote_addr or "0.0.0.0", row["name"])
    flash("Rol șters.", "success")
    return redirect(url_for("admin.users"))
