"""Autorizari (role -> nav) matrix page on admin_bp.

Imported for side effects in app.py before admin_bp is registered.
"""
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

import authz
from nav_registry import NAV_REGISTRY, GROUPS
from blueprints.auth import _log, admin_bp, require_role


@admin_bp.route("/authorizations", methods=["GET", "POST"])
@require_role("admin")
def authorizations():
    roles = [r for r in authz.all_roles() if r["name"] != authz.ADMIN_ROLE]

    if request.method == "POST":
        from flask import current_app, abort
        from flask_wtf.csrf import validate_csrf
        if current_app.config.get("WTF_CSRF_ENABLED", True):
            try:
                validate_csrf(request.form.get("csrf_token"))
            except Exception:
                abort(403)

        grants = {r["name"]: [] for r in roles}
        for field in request.form:
            # fields look like "grant:<role>:<navkey>"
            if not field.startswith("grant:"):
                continue
            parts = field.split(":", 2)
            if len(parts) != 3:
                continue
            _, role_name, nav_key = parts
            if role_name in grants:
                grants[role_name].append(nav_key)
        authz.save_matrix(grants)
        _log(current_user.id, "authz_saved", request.remote_addr or "0.0.0.0")
        flash("Autorizări salvate.", "success")
        return redirect(url_for("admin.authorizations"))

    matrix = authz.get_matrix()  # {role_name: set(nav_key)}
    groups = []
    for g in GROUPS:
        items = [i for i in NAV_REGISTRY if i.group == g]
        if items:
            groups.append({"group": g, "items": items})
    return render_template(
        "admin/authorizations.html", roles=roles, groups=groups, matrix=matrix,
    )
