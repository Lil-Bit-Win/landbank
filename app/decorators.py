"""
Role-based access control decorators.

Usage:
    @login_required
    @role_required("admin")
    def some_view():
        ...

    @login_required
    @kb_editor_required
    def kb_new():
        ...
"""
from functools import wraps
from flask import abort, current_app, request
from flask_login import current_user

from app.api_utils import api_error


def _deny(status_code):
    # API callers get the standard JSON envelope; browser callers get the
    # app's own styled error pages via the 401/403 handlers registered in
    # app/__init__.py (added by this patch — previously only 404/500/429
    # were registered, so browser 403s fell through to Flask's default page).
    if status_code == 403:
        # FEATURE 1 (audit logging): every forbidden-access attempt is
        # recorded, not just successful CRUD. 401s are excluded here —
        # they're pre-authentication and extremely high-volume/low-signal
        # (e.g. every logged-out page view), so logging them would mostly
        # add noise rather than a useful audit trail.
        #
        # AUDIT FIX: guarded — a failure here must never turn a clean
        # 403 (access correctly denied) into an unrelated 500, and must
        # never mask the real denial response.
        try:
            from app.logging_config import log_audit
            log_audit(
                "FORBIDDEN_ACCESS_ATTEMPT",
                metadata={"path": request.path, "method": request.method},
            )
        except Exception:
            current_app.logger.exception("audit_log_failed")
    if request.path.startswith("/api/"):
        message = "Authentication required" if status_code == 401 else "Forbidden: insufficient role"
        return api_error(message, status_code=status_code)
    abort(status_code)


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return _deny(401)
            if current_user.role not in roles:
                return _deny(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def permission_required(permission_name):
    """
    FEATURE 3 (enterprise RBAC+): finer-grained alternative to
    role_required(). Existing roles ("admin"/"agent") are unchanged —
    this only adds a named-capability layer on top of them, backed by
    app.services.permission_service.has_permission() (DB-configurable,
    with a hardcoded fallback that mirrors current behavior — see that
    module's docstring).

    Usage:
        @login_required
        @permission_required("delete_kb")
        def kb_delete(article_id):
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            from app.services.permission_service import has_permission

            if not current_user.is_authenticated:
                return _deny(401)
            if not has_permission(current_user.role, permission_name):
                return _deny(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def kb_editor_required(f):
    """
    FIX 1: KB create/edit access is configurable via ALLOWED_KB_EDITOR_ROLES
    (defaults to ["admin", "agent"] — i.e. current behavior is preserved
    unless an operator explicitly restricts it).
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return _deny(401)
        allowed = current_app.config.get("ALLOWED_KB_EDITOR_ROLES", ["admin", "agent"])
        if current_user.role not in allowed:
            return _deny(403)
        return f(*args, **kwargs)
    return wrapped


def check_kb_ownership(article):
    """
    HARDENING FIX (IDOR / object-level authorization).

    `kb_editor_required` only checks the caller's *role* — it never checks
    whether this specific article belongs to them. Without this, any
    authenticated agent could edit or corrupt another agent's article just
    by guessing/incrementing the numeric `article_id` in the URL — a
    classic IDOR, since the only thing standing between "my article" and
    "someone else's article" was an unguarded integer.

    Rule applied (matches this app's data model — every KB article is a
    system-wide shared object, not a private one, but it does record an
    owner via `created_by`):
      - admins may edit any article (role-based access to a shared
        resource, per existing design)
      - everyone else may only edit an article they themselves created

    Called after the article has already been fetched by the route (so a
    missing article still 404s first, rather than leaking a 403 for an
    ID that doesn't exist). Aborts with 403 on violation; returns None
    (falls through) when the caller is authorized.
    """
    if current_user.role == "admin":
        return None
    if article.created_by != current_user.id:
        try:
            from app.logging_config import log_audit
            log_audit(
                "UNAUTHORIZED_ACCESS_ATTEMPT",
                resource_type="KnowledgeBase",
                resource_id=article.id,
                metadata={"reason": "not_owner"},
            )
        except Exception:
            current_app.logger.exception("audit_log_failed")
        return _deny(403)
    return None
