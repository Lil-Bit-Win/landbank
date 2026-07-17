"""
Shared extension instances.

Kept in their own module (not in the target file tree, but required to
avoid circular imports between app/__init__.py, models, and routes) so
models.py and routes/*.py can import `db` without importing the app
factory itself.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def rate_limit_key():
    """
    HARDENING FIX (rate limiting): keying purely on remote address is
    unsafe for real deployments. Many legitimate users share one IP
    behind NAT, a corporate proxy, or a mobile carrier, so an IP-only
    limit lets one heavy user 429 everyone else on that address, while a
    single bad actor can rotate IPs to dodge the limit entirely.

    Authenticated requests are keyed per-user instead (each account gets
    its own quota, independent of any shared IP). Unauthenticated
    requests (e.g. hitting /login before a session exists) fall back to
    the remote address, since there is no user identity yet to key on.
    """
    if current_user.is_authenticated:
        return f"user:{current_user.id}"
    return get_remote_address()


limiter = Limiter(key_func=rate_limit_key)


def safe_commit():
    """
    CHECK 6 fix: explicit local commit/rollback instead of relying solely
    on the global 500 handler. Rolls back immediately on failure so the
    session isn't left dangling, then re-raises so the caller (route or
    global error handler) still sees and logs the original exception —
    nothing is silently swallowed.
    """
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
