# app/auth.py
"""
Authentication and administration module.

Exports:
    auth_bp      â€” Blueprint mounted at /auth  (login, logout, password routes)
    admin_bp     â€” Blueprint mounted at /admin (user management, admin-only)
    login_manager â€” Flask-Login LoginManager, call login_manager.init_app(app)
    csrf         â€” Flask-WTF CSRFProtect, call csrf.init_app(app)
    require_role â€” decorator factory for role-based access control
"""

import hashlib
import logging
import os
import secrets
import smtplib
import sqlite3
import ssl
import threading
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, validate_csrf
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import BooleanField, PasswordField, SelectField, StringField
from wtforms.validators import DataRequired, EqualTo, Length

from paths import DB_PATH

# â”€â”€ Flask extensions (bound to app via init_app in app.py) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "AutentificaÈ›i-vÄƒ pentru a accesa aceastÄƒ paginÄƒ."
login_manager.login_message_category = "warning"

csrf = CSRFProtect()

# â”€â”€ In-memory rate limiter for login attempts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_rate_lock = threading.Lock()
_rate_store: dict = {}  # ip -> [unix_timestamps]
_RATE_LIMIT = 10
_RATE_WINDOW = 900  # 15 minutes


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        ts = [t for t in _rate_store.get(ip, []) if now - t < _RATE_WINDOW]
        _rate_store[ip] = ts
        return len(ts) < _RATE_LIMIT


def _record_failed(ip: str) -> None:
    with _rate_lock:
        _rate_store.setdefault(ip, []).append(time.time())


def _clear_rate(ip: str) -> None:
    with _rate_lock:
        _rate_store.pop(ip, None)


# â”€â”€ User model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.email = row["email"]
        self.password_hash = row["password_hash"]
        self.role = row["role"]
        self._is_active = bool(row["is_active"])
        self.force_pw_reset = bool(row["force_pw_reset"])

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self._is_active

    @staticmethod
    def _conn():
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
        return c

    @staticmethod
    def get(user_id):
        with User._conn() as c:
            row = c.execute(
                "SELECT id, username, email, password_hash, role, is_active, force_pw_reset"
                " FROM users WHERE id=?",
                (int(user_id),),
            ).fetchone()
        return User(row) if row else None

    @staticmethod
    def get_by_username(username):
        with User._conn() as c:
            row = c.execute(
                "SELECT id, username, email, password_hash, role, is_active, force_pw_reset"
                " FROM users WHERE username=? COLLATE NOCASE",
                (username,),
            ).fetchone()
        return User(row) if row else None

    @staticmethod
    def get_by_email(email):
        with User._conn() as c:
            row = c.execute(
                "SELECT id, username, email, password_hash, role, is_active, force_pw_reset"
                " FROM users WHERE email=? COLLATE NOCASE",
                (email,),
            ).fetchone()
        return User(row) if row else None


@login_manager.user_loader
def _load_user(user_id):
    return User.get(user_id)


@login_manager.unauthorized_handler
def _unauthorized():
    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"error": "Unauthorized", "code": 401}), 401
    return redirect(url_for("auth.login", next=request.full_path))


# â”€â”€ Auth audit log â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _log(user_id, event: str, ip: str, details: str = "") -> None:
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.execute(
                "INSERT INTO auth_log (user_id, event, ip_address, details) VALUES (?,?,?,?)",
                (user_id, event, ip, details),
            )
    except Exception:
        _log_mail.warning("auth_log DB write failed", exc_info=True)


_log_mail = logging.getLogger(__name__)


def _smtp_send(to_email: str, subject: str, body: str) -> bool:
    """Shared SMTP sender â€” mirrors the working VPS test script exactly."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        _log_mail.warning("SMTP_HOST not set â€” email not sent to %s", to_email)
        return False
    try:
        port = int(os.environ.get("SMTP_PORT", 587))
        user = os.environ.get("SMTP_USER", "")
        pw = os.environ.get("SMTP_PASSWORD", "")
        from_addr = os.environ.get("SMTP_FROM", user)
        _log_mail.info("SMTP: connecting to %s:%s to send to %s", host, port, to_email)
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_email
        msg.set_content(body, charset="utf-8")
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if port == 587:
                smtp.starttls(context=ctx)
            if user and pw:
                smtp.login(user, pw)
            smtp.send_message(msg)
        _log_mail.info("SMTP: sent OK to %s", to_email)
        return True
    except Exception:
        _log_mail.exception("SMTP send failed to %s", to_email)
        return False


# â”€â”€ Email sender (degrades gracefully if SMTP not configured) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _send_reset_email(to_email: str, reset_url: str) -> bool:
    body = (
        "BunÄƒ,\n\n"
        "AÈ›i solicitat resetarea parolei pentru contul Torb Logistic.\n\n"
        f"AccesaÈ›i link-ul urmÄƒtor (valid 1 orÄƒ):\n{reset_url}\n\n"
        "DacÄƒ nu aÈ›i solicitat aceastÄƒ resetare, ignoraÈ›i acest email."
    )
    return _smtp_send(to_email, "Resetare parolÄƒ â€” Torb Logistic", body)


def _send_new_password_email(to_email: str, username: str, new_password: str) -> bool:
    body = (
        f"BunÄƒ, {username},\n\n"
        "Parola dvs. pentru contul Torb Logistic a fost schimbatÄƒ cu succes.\n\n"
        f"Noua parolÄƒ: {new_password}\n\n"
        "DacÄƒ nu aÈ›i iniÈ›iat aceastÄƒ schimbare, contactaÈ›i administratorul imediat."
    )
    return _smtp_send(to_email, "ParolÄƒ schimbatÄƒ â€” Torb Logistic", body)


# â”€â”€ WTForms â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Parolă", validators=[DataRequired()])
    remember = BooleanField("Ține-mă minte")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Parola curentÄƒ", validators=[DataRequired()])
    new_password = PasswordField(
        "ParolÄƒ nouÄƒ", validators=[DataRequired(), Length(min=6)]
    )
    confirm = PasswordField(
        "ConfirmÄƒ parola", validators=[DataRequired(), EqualTo("new_password")]
    )


class ResetRequestForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])


class ResetPasswordForm(FlaskForm):
    new_password = PasswordField(
        "ParolÄƒ nouÄƒ", validators=[DataRequired(), Length(min=6)]
    )
    confirm = PasswordField(
        "ConfirmÄƒ parola", validators=[DataRequired(), EqualTo("new_password")]
    )


class UserForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=32)])
    email = StringField("Email", validators=[DataRequired()])
    role = SelectField(
        "Rol",
        choices=[("manager", "Manager"), ("viewer", "Viewer"), ("admin", "Admin")],
    )


class EditUserForm(UserForm):
    is_active = BooleanField("Activ")


# â”€â”€ Role-based access decorator â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def require_role(*roles):
    """Decorator â€” requires authentication AND one of the given roles."""

    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)

        return wrapped

    return decorator


# â”€â”€ Blueprints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# â”€â”€ Auth routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("analytics.dashboard"))

    form = LoginForm()
    error = None

    if form.validate_on_submit():
        ip = request.remote_addr or "0.0.0.0"
        if not _check_rate_limit(ip):
            error = "Prea multe Ã®ncercÄƒri eÈ™uate. ÃŽncercaÈ›i din nou Ã®n 15 minute."
        else:
            user = User.get_by_username(form.username.data.strip())
            if user and user.is_active and check_password_hash(
                user.password_hash, form.password.data
            ):
                _clear_rate(ip)
                login_user(user, remember=form.remember.data)
                _log(user.id, "login_ok", ip)
                try:
                    with sqlite3.connect(DB_PATH) as c:
                        c.execute(
                            "UPDATE users SET last_login_at=datetime('now') WHERE id=?",
                            (user.id,),
                        )
                except Exception:
                    _log_mail.warning("last_login_at update failed for user %s", user.id, exc_info=True)
                if user.force_pw_reset:
                    return redirect(url_for("auth.change_password"))
                next_url = request.args.get("next") or ""
                parsed = urlparse(next_url)
                if not parsed.scheme and not parsed.netloc and next_url and next_url.startswith('/') and not next_url.startswith('//'):
                    return redirect(next_url)
                return redirect(url_for("analytics.dashboard"))
            else:
                _record_failed(ip)
                _log(
                    user.id if user else None,
                    "login_fail",
                    ip,
                    form.username.data.strip(),
                )
                error = "CredenÈ›iale incorecte sau cont inactiv."

    return render_template("auth/login.html", form=form, error=error)


@auth_bp.route("/logout")
@login_required
def logout():
    _log(current_user.id, "logout", request.remote_addr or "0.0.0.0")
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    error = None

    if form.validate_on_submit():
        if not check_password_hash(current_user.password_hash, form.current_password.data):
            error = "Parola curentÄƒ este incorectÄƒ."
        else:
            new_password = form.new_password.data
            new_hash = generate_password_hash(new_password)
            _send_new_password_email(current_user.email, current_user.username, new_password)
            try:
                with sqlite3.connect(DB_PATH) as c:
                    c.execute(
                        "UPDATE users SET password_hash=?, force_pw_reset=0,"
                        " updated_at=datetime('now') WHERE id=?",
                        (new_hash, current_user.id),
                    )
                _log(current_user.id, "pw_change", request.remote_addr or "0.0.0.0")
                current_user.force_pw_reset = False  # refresh in-memory object
                flash("Parola a fost schimbatÄƒ cu succes.", "success")
                return redirect(url_for("analytics.dashboard"))
            except Exception as exc:
                error = f"Eroare: {exc}"

    return render_template(
        "auth/change_password.html",
        form=form,
        error=error,
        forced=current_user.force_pw_reset,
    )


@auth_bp.route("/reset-request", methods=["GET", "POST"])
def reset_request():
    form = ResetRequestForm()
    sent = False

    if form.validate_on_submit():
        user = User.get_by_email(form.email.data.strip())
        if user:
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            expires = datetime.utcnow() + timedelta(hours=1)
            try:
                with sqlite3.connect(DB_PATH) as c:
                    c.execute(
                        "UPDATE password_reset_tokens SET used=1 WHERE user_id=?",
                        (user.id,),
                    )
                    c.execute(
                        "INSERT INTO password_reset_tokens"
                        " (user_id, token_hash, expires_at) VALUES (?,?,?)",
                        (user.id, token_hash, expires.strftime("%Y-%m-%d %H:%M:%S")),
                    )
                reset_url = url_for("auth.reset_confirm", token=raw_token, _external=True)
                _send_reset_email(user.email, reset_url)
            except Exception:
                _log_mail.exception("Password reset token creation failed for user %s", user.id)
        sent = True  # always show â€” prevents email enumeration

    return render_template(
        "auth/reset_request.html",
        form=form,
        sent=sent,
        smtp_ok=bool(os.environ.get("SMTP_HOST")),
    )


@auth_bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_confirm(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        row = c.execute(
            "SELECT * FROM password_reset_tokens"
            " WHERE token_hash=? AND used=0 AND expires_at > datetime('now')",
            (token_hash,),
        ).fetchone()

    if not row:
        return render_template("auth/reset_confirm.html", form=None, invalid=True)

    form = ResetPasswordForm()
    if form.validate_on_submit():
        new_hash = generate_password_hash(form.new_password.data)
        try:
            with sqlite3.connect(DB_PATH) as c:
                c.execute(
                    "UPDATE users SET password_hash=?, force_pw_reset=0,"
                    " updated_at=datetime('now') WHERE id=?",
                    (new_hash, row["user_id"]),
                )
                c.execute(
                    "UPDATE password_reset_tokens SET used=1 WHERE id=?", (row["id"],)
                )
            flash("Parola a fost resetatÄƒ. VÄƒ puteÈ›i autentifica.", "success")
            return redirect(url_for("auth.login"))
        except Exception as exc:
            return render_template(
                "auth/reset_confirm.html", form=form, invalid=False, error=str(exc)
            )

    return render_template("auth/reset_confirm.html", form=form, invalid=False)


# â”€â”€ Admin routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@admin_bp.route("/users")
@require_role("admin")
def users():
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT id, username, email, role, is_active, last_login_at, created_at"
            " FROM users ORDER BY id"
        ).fetchall()
    return render_template("admin/users.html", users=rows)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@require_role("admin")
def user_new():
    form = UserForm()
    if form.validate_on_submit():
        raw_pw = secrets.token_urlsafe(10)
        pw_hash = generate_password_hash(raw_pw)
        try:
            with sqlite3.connect(DB_PATH) as c:
                c.execute(
                    "INSERT INTO users (username, email, password_hash, role, force_pw_reset)"
                    " VALUES (?,?,?,?,1)",
                    (
                        form.username.data.strip(),
                        form.email.data.strip(),
                        pw_hash,
                        form.role.data,
                    ),
                )
            _log(
                current_user.id,
                "user_created",
                request.remote_addr or "0.0.0.0",
                form.username.data.strip(),
            )
            return render_template(
                "admin/user_created.html",
                username=form.username.data.strip(),
                password=raw_pw,
                reset=False,
            )
        except sqlite3.IntegrityError:
            form.username.errors.append("Username sau email deja existent.")
    return render_template(
        "admin/user_form.html",
        form=form,
        title="Utilizator nou",
        action=url_for("admin.user_new"),
    )


@admin_bp.route("/users/<int:uid>/edit", methods=["GET", "POST"])
@require_role("admin")
def user_edit(uid):
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        abort(404)

    form = EditUserForm()
    if request.method == "GET":
        form.username.data = row["username"]
        form.email.data = row["email"]
        form.role.data = row["role"]
        form.is_active.data = bool(row["is_active"])

    if form.validate_on_submit():
        try:
            with sqlite3.connect(DB_PATH) as c:
                c.execute(
                    "UPDATE users SET username=?, email=?, role=?, is_active=?,"
                    " updated_at=datetime('now') WHERE id=?",
                    (
                        form.username.data.strip(),
                        form.email.data.strip(),
                        form.role.data,
                        1 if form.is_active.data else 0,
                        uid,
                    ),
                )
            flash("Utilizatorul a fost actualizat.", "success")
            return redirect(url_for("admin.users"))
        except sqlite3.IntegrityError:
            form.username.errors.append("Username sau email deja existent.")

    return render_template(
        "admin/user_form.html",
        form=form,
        title="Editare utilizator",
        action=url_for("admin.user_edit", uid=uid),
    )


@admin_bp.route("/users/<int:uid>/reset-password", methods=["POST"])
@require_role("admin")
def user_reset_password(uid):
    try:
        validate_csrf(request.form.get("csrf_token"))
    except Exception:
        abort(403)
    raw_pw = secrets.token_urlsafe(10)
    pw_hash = generate_password_hash(raw_pw)
    with sqlite3.connect(DB_PATH) as c:
        c.execute(
            "UPDATE users SET password_hash=?, force_pw_reset=1,"
            " updated_at=datetime('now') WHERE id=?",
            (pw_hash, uid),
        )
        row = c.execute("SELECT username, email FROM users WHERE id=?", (uid,)).fetchone()
    username = row[0] if row else f"User {uid}"
    email = row[1] if row and row[1] else None
    _log(current_user.id, "pw_reset", request.remote_addr or "0.0.0.0", username)
    if email:
        threading.Thread(
            target=_send_new_password_email,
            args=(email, username, raw_pw),
            daemon=True,
        ).start()
    return render_template(
        "admin/user_created.html", username=username, password=raw_pw, reset=True
    )


@admin_bp.route("/users/<int:uid>/toggle-active", methods=["POST"])
@require_role("admin")
def user_toggle_active(uid):
    try:
        validate_csrf(request.form.get("csrf_token"))
    except Exception:
        abort(403)
    if uid == current_user.id:
        flash("Nu vÄƒ puteÈ›i dezactiva propriul cont.", "warning")
        return redirect(url_for("admin.users"))
    with sqlite3.connect(DB_PATH) as c:
        c.execute(
            "UPDATE users SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END"
            " WHERE id=?",
            (uid,),
        )
    return redirect(url_for("admin.users"))

