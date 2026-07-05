import sys
import os
import json
import datetime
import logging

# Keep sys.path insert at module level so blueprint files can import db, queries, etc.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, redirect, url_for, render_template
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(_env_path)


def create_app(test_config=None):
    import db
    import queries
    from migrate import apply_migrations
    from blueprints.auth import admin_bp, auth_bp, csrf, login_manager
    from blueprints import admin_db  # noqa: F401 — attaches /admin/db routes to admin_bp
    from blueprints.analytics import analytics_bp
    from blueprints.bonus import bonus_bp
    from blueprints.pricing import pricing_bp
    from blueprints.forecast import forecast_bp
    from blueprints.actualizare import actualizare_bp
    from blueprints.reports import reports_bp
    from blueprints.solduri import solduri_bp
    from blueprints.stocuri_emag import stocuri_emag_bp
    from blueprints.stocuri_shopify import stocuri_shopify_bp
    from blueprints.campanii import campanii_bp
    from blueprints.postari import postari_bp
    from blueprints.pachete import pachete_bp

    # ── Logging ──────────────────────────────────────────────────────────────
    from logging_config import setup_logging
    setup_logging()
    logger = logging.getLogger(__name__)

    # ── Secret key ───────────────────────────────────────────────────────────
    _secret_key = os.environ.get('FLASK_SECRET_KEY', '')
    if not _secret_key or _secret_key == 'change-me-set-FLASK_SECRET_KEY-in-env':
        import warnings
        warnings.warn(
            "FLASK_SECRET_KEY is not set or uses the insecure default. "
            "Sessions are forgeable. Set a strong random key in .env before deploying.",
            stacklevel=2,
        )
        _secret_key = 'change-me-set-FLASK_SECRET_KEY-in-env'

    # ── App creation ─────────────────────────────────────────────────────────
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), 'static'),
    )
    app.config.update(
        SECRET_KEY=_secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', '0') == '1',
        REMEMBER_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', '0') == '1',
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=8),
        REMEMBER_COOKIE_DURATION=datetime.timedelta(days=7),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE='Lax',
        WTF_CSRF_CHECK_DEFAULT=False,
    )
    if test_config:
        app.config.update(test_config)

    # ── Reverse-proxy awareness ──────────────────────────────────────────────
    # nginx terminates TLS and sets X-Forwarded-For / X-Forwarded-Proto (one hop).
    # Without this, request.remote_addr is always 127.0.0.1 (breaks the login rate
    # limiter + audit-log IPs) and Flask can't tell the request arrived over HTTPS.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # ── Extensions ───────────────────────────────────────────────────────────
    login_manager.init_app(app)
    csrf.init_app(app)
    app.teardown_appcontext(db.close_request_db)

    # ── Blueprints ───────────────────────────────────────────────────────────
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(bonus_bp)
    app.register_blueprint(pricing_bp)
    app.register_blueprint(forecast_bp)
    app.register_blueprint(actualizare_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(solduri_bp)
    app.register_blueprint(stocuri_emag_bp)
    app.register_blueprint(stocuri_shopify_bp)
    app.register_blueprint(campanii_bp)
    app.register_blueprint(postari_bp)
    app.register_blueprint(pachete_bp)

    # ── Startup tasks (skipped in test mode) ─────────────────────────────────
    if not app.config.get('TESTING'):
        try:
            queries.ensure_cond_resolved()
        except Exception:
            logger.warning("ensure_cond_resolved failed at startup", exc_info=True)
        with app.app_context():
            apply_migrations()
        try:
            from automations.auto_posts.scheduler import start_background_scheduler
            start_background_scheduler()
        except ImportError:
            logger.warning("auto_posts scheduler not available — skipping")

    # ── Auth gate ────────────────────────────────────────────────────────────
    @app.before_request
    def _require_auth():
        ep = request.endpoint or ''
        if ep in ('static', 'healthz') or ep.endswith('.static'):
            return
        if request.blueprint == 'auth':
            return
        if not current_user.is_authenticated:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized', 'code': 401}), 401
            return redirect(url_for('auth.login', next=request.full_path))
        if current_user.force_pw_reset and request.endpoint != 'auth.change_password':
            return redirect(url_for('auth.change_password'))

    @app.route('/healthz')
    def healthz():
        return jsonify({'ok': True}), 200

    # ── Template filters ─────────────────────────────────────────────────────
    RON_USD = 4.55

    @app.template_filter('ron')
    def fmt_ron(value):
        if value is None:
            return '—'
        try:
            v = float(value)
            if abs(v) >= 1_000_000:
                return f"{v / 1_000_000:.2f}M RON"
            return f"{int(v):,} RON".replace(',', '.')
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter('usd')
    def fmt_usd(value, rate=None):
        if value is None:
            return '—'
        try:
            v = float(value) / (rate or RON_USD)
            if abs(v) >= 1_000_000:
                return f"${v / 1_000_000:.2f}M"
            if abs(v) >= 1_000:
                return f"${v:,.0f}".replace(',', ' ')
            return f"${v:,.0f}"
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter('pct')
    def fmt_pct(value):
        if value is None:
            return '—'
        try:
            return f"{float(value):.1f}%"
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter('delta_class')
    def delta_class(value):
        if value is None:
            return 'text-secondary'
        return 'text-success' if float(value) >= 0 else 'text-danger'

    @app.template_filter('churn_badge')
    def churn_badge(zile):
        if zile is None:
            return '<span class="badge bg-secondary">—</span>'
        z = int(zile)
        if z >= 30:
            return f'<span class="badge bg-danger">{z}z</span>'
        if z >= 16:
            return f'<span class="badge bg-warning text-dark">{z}z</span>'
        return f'<span class="badge bg-success">{z}z</span>'

    @app.template_filter('days_until')
    def days_until(iso_date):
        if not iso_date:
            return None
        try:
            d = datetime.datetime.strptime(str(iso_date)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
        return (d - datetime.date.today()).days

    # ── Context processor ────────────────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        from feature_flags import SHOW_TESTING
        cy = datetime.date.today().year
        return {
            'current_year': cy,
            'today': datetime.date.today(),
            'display_years': [cy - 2, cy - 1, cy],
            'sku_cod_mare': queries.get_sku_cod_mare_map(),
            'show_testing': SHOW_TESTING,
        }

    # ── Error handlers ───────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Forbidden', 'code': 403}), 403
        return render_template('403.html'), 403

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        logger.exception("Unhandled exception on %s %s", request.method, request.path)
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error'}), 500
        return render_template('500.html'), 500

    # ── Security headers ─────────────────────────────────────────────────────
    # CSP: pragmatic 'self'-based policy. All assets are served same-origin from
    # static/ (no CDN), so this blocks every externally-hosted script/style/frame
    # and external exfiltration. 'unsafe-inline' is required because templates use
    # ~25 inline <script> blocks, 99 inline event handlers, and many inline styles;
    # a strict nonce/hash policy would need a full template refactor (follow-up).
    _CSP = "; ".join([
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'self'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ])

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        resp.headers.setdefault(
            'Strict-Transport-Security', 'max-age=31536000; includeSubDomains'
        )
        resp.headers.setdefault('Content-Security-Policy', _CSP)
        return resp

    # ── OPENCLAW AGENT PROXY ─────────────────────────────────────────────────
    # The browser POSTs a prompt; Flask runs the OpenClaw agent CLI as the
    # `openclaw` user (its gateway/auth/device state lives in that user's home,
    # unreadable by www-data) and returns the reply as JSON. No secret reaches
    # the client. CSRF via the X-CSRFToken header. The wrapper script and the
    # sudoers rule are documented in docs/TECHNICAL.md.
    @app.route('/admin/openclaw-ask', methods=['POST'])
    def openclaw_ask():
        if not current_user.is_authenticated or getattr(current_user, 'role', '') != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403

        import subprocess
        user_prompt = (request.get_json(silent=True) or {}).get('message', '').strip()
        if not user_prompt:
            return jsonify({'error': 'Mesaj lipsa.'}), 400
        if len(user_prompt) > 4000:
            return jsonify({'error': 'Mesaj prea lung (max 4000 caractere).'}), 400

        # Stable per-admin session id keeps each admin's conversation separate.
        session_id = f"torb-admin-{getattr(current_user, 'id', 'anon')}"
        ask_bin = os.environ.get('OPENCLAW_ASK_BIN', '/usr/local/bin/torb-openclaw-ask')
        timeout_s = int(os.environ.get('OPENCLAW_TIMEOUT', '120'))

        try:
            proc = subprocess.run(
                ['sudo', '-n', '-u', 'openclaw', ask_bin, session_id, user_prompt],
                capture_output=True, text=True, timeout=timeout_s,
            )
        except FileNotFoundError:
            return jsonify({'error': 'OpenClaw nu este disponibil in acest mediu.'}), 503
        except subprocess.TimeoutExpired:
            return jsonify({'error': f'OpenClaw a depasit timpul de raspuns ({timeout_s}s).'}), 504

        if proc.returncode != 0:
            logger.error("OpenClaw CLI failed rc=%s stderr=%s", proc.returncode, proc.stderr[:800])
            return jsonify({'error': 'OpenClaw a returnat o eroare.'}), 502

        try:
            data = json.loads(proc.stdout)
        except (ValueError, TypeError):
            logger.error("OpenClaw CLI non-JSON output: %s", proc.stdout[:800])
            return jsonify({'error': 'Raspuns invalid de la OpenClaw.'}), 502

        if data.get('status') != 'ok':
            return jsonify({'error': data.get('summary') or 'OpenClaw nu a putut procesa cererea.'}), 502

        payloads = (data.get('result') or {}).get('payloads') or []
        reply = payloads[0].get('text', '') if payloads else ''
        return jsonify({'reply': reply})
    return app


# Default instance — used by `python app.py` and `flask run`
app = create_app()

if __name__ == '__main__':
    app.run(
        debug=os.environ.get('FLASK_DEBUG', '0') == '1',
        host='127.0.0.1',
        port=int(os.environ.get('PORT', '5000')),
    )
