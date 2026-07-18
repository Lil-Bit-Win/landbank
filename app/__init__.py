from flask import Flask, request, redirect, url_for, render_template
from flask_login import current_user
from flask_limiter.errors import RateLimitExceeded

from .config import Config, INSECURE_DEFAULT_SECRET_KEY
from .extensions import db, migrate, login_manager, csrf, limiter
from .logging_config import configure_logging, log_event
from .api_utils import api_error


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    configure_logging(app)

    if app.config.get("SECRET_KEY") == INSECURE_DEFAULT_SECRET_KEY:
        # Non-fatal here on purpose: create_app() is also used by tests,
        # seed.py, and `flask db ...`. The hard failure for real
        # deployments lives in run.py's assert_production_secret_key().
        app.logger.warning(
            "SECURITY WARNING: running with the default insecure SECRET_KEY. "
            "Set SECRET_KEY in your environment before deploying (FIX 9)."
        )

    # --- Initialize extensions ---
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."


        # --- AUTO DATABASE SETUP + DEFAULT USERS (FREE PLAN FIX) ---
    import os
    from app.models.user import User

    with app.app_context():
        try:
            db.create_all()

            if not User.query.filter_by(username="admin").first():
                admin = User(username="admin", role="admin")
                admin.set_password(os.environ.get("SEED_ADMIN_PASSWORD", "admin123"))
                db.session.add(admin)

            if not User.query.filter_by(username="agent").first():
                agent = User(username="agent", role="agent")
                agent.set_password(os.environ.get("SEED_AGENT_PASSWORD", "agent123"))
                db.session.add(agent)

            db.session.commit()
            app.logger.info("✅ Default users ensured")

        except Exception as e:
            app.logger.error(f"❌ Error creating default users: {e}")    


    # FIX 3: models must be imported here (even though unused directly)
    # so Flask-Migrate's autogenerate can see them via db.metadata when
    # `flask db migrate` introspects the models.
    from .models.user import User
    from .models.kb import KnowledgeBase  # noqa: F401
    from .models.sop import SOP  # noqa: F401
    from .models.audit_log import AuditLog  # noqa: F401
    from .models.permission import Permission, RolePermission  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        # API clients get the standard JSON envelope instead of an HTML redirect.
        if request.path.startswith("/api/"):
            return api_error("Authentication required", status_code=401)
        return redirect(url_for("auth.login", next=request.path))

    # --- Register blueprints ---
    from .routes.auth_routes import auth_bp
    from .routes.main_routes import main_bp
    from .routes.kb_routes import kb_bp
    from .routes.sop_routes import sop_bp
    from .routes.api_routes import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(kb_bp)
    app.register_blueprint(sop_bp)
    app.register_blueprint(api_bp)

    # JSON API is not form/cookie-driven, so it is exempt from CSRF
    # (which protects the HTML forms served by the other blueprints).
    csrf.exempt(api_bp)

    # FIX 1: expose KB-edit permission to templates so Edit/Add links are
    # only shown to users who are actually allowed to use them.
    @app.context_processor
    def inject_permissions():
        def can_edit_kb():
            if not current_user.is_authenticated:
                return False
            allowed = app.config.get("ALLOWED_KB_EDITOR_ROLES", ["admin", "agent"])
            return current_user.role in allowed
        return dict(can_edit_kb=can_edit_kb)

    # FIX 6 / patch: standardized error handling — no raw crashes, consistent
    # JSON envelope for the API, rendered pages for the browser. 500s also
    # roll back any broken DB session and are logged.
    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return api_error("Not found", status_code=404)
        return render_template("errors/404.html"), 404

    # PATCH: role_required()/kb_editor_required() in decorators.py call
    # abort(401)/abort(403) for browser requests. Previously there was no
    # handler for either status, so an authenticated user hitting a
    # role-restricted page (e.g. an agent opening a raw SOP-edit URL) fell
    # through to Flask's default unstyled Werkzeug error page — even though
    # a comment in decorators.py claimed these were "rendered by the
    # handlers registered... in app/__init__.py". That claim is now true.
    @app.errorhandler(401)
    def unauthorized_error(_error):
        if request.path.startswith("/api/"):
            return api_error("Authentication required", status_code=401)
        return redirect(url_for("auth.login", next=request.path))

    @app.errorhandler(403)
    def forbidden_error(_error):
        if request.path.startswith("/api/"):
            return api_error("Forbidden: insufficient role", status_code=403)
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        app.logger.error(f"Unhandled server error on {request.path}: {error}")
        if request.path.startswith("/api/"):
            return api_error("Internal server error", status_code=500)
        return render_template("errors/500.html"), 500

    # AUDIT NOTE (Gap 5 — no leaks): verified by direct testing that
    # Flask already routes any uncaught, non-HTTP exception (e.g. a bare
    # ValueError from a bug in a view) through the errorhandler(500)
    # above when DEBUG=False — Flask converts it to InternalServerError
    # before error-handler lookup, so nothing extra was needed here. An
    # earlier attempt at adding a blanket errorhandler(Exception) as
    # "extra" defense-in-depth was reverted: re-raising HTTPExceptions
    # from inside it to let 413/400/405/etc. fall through to their normal
    # handling does not work the way it looks like it should — Flask
    # does not re-catch an exception raised by its own error handler, so
    # it escaped instead of being rendered as the correct status code
    # (verified by test_oversized_payload_is_rejected going from 413 to
    # an unhandled 500). Confirmed via test suite: don't add
    # "extra" error handling without re-verifying nothing already-correct
    # breaks.

    # CHECK 3: rate-limit responses also use the API envelope on /api/*.
    @app.errorhandler(RateLimitExceeded)
    def rate_limited(_error):
        app.logger.warning(f"Rate limit exceeded for {request.remote_addr} on {request.path}")
        if request.path.startswith("/api/"):
            return api_error("Too many requests — please slow down.", status_code=429)
        return render_template("errors/500.html"), 429

    # FIX 7: security headers on every response.
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

    # FEATURE 4 (observability): request-timing middleware. Separate
    # before/after_request pair rather than folding into
    # set_security_headers() above, so the two concerns (headers vs.
    # observability) stay independently readable and removable.
    import time

    @app.before_request
    def _start_request_timer():
        from flask import g
        try:
            g._request_start_time = time.monotonic()
        except Exception:
            pass

    @app.after_request
    def _log_request_metrics(response):
        from flask import g
        from app.metrics import record_request

        # AUDIT FIX (Gap 10 — graceful degradation): this middleware runs
        # on every single response. Without this guard, a bug in logging
        # or metrics (e.g. a bad log_event() call, a metrics counter
        # error) would turn an otherwise-successful response into a 500
        # for the user — the observability layer must never be able to
        # take down the primary request/response flow.
        try:
            duration_ms = None
            start = getattr(g, "_request_start_time", None)
            if start is not None:
                duration_ms = round((time.monotonic() - start) * 1000, 2)

            log_event(
                "http_request",
                method=request.method,
                path=request.path,
                endpoint=request.endpoint,
                status=response.status_code,
                duration_ms=duration_ms,
            )
            record_request(request.endpoint, response.status_code, duration_ms)
        except Exception:
            app.logger.exception("request_metrics_logging_failed")
        return response

    return app
