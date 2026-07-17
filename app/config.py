import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


INSECURE_DEFAULT_SECRET_KEY = "dev-insecure-key-change-me"

# HARDENING FIX (environment): the app is considered "production" whenever
# it isn't explicitly marked otherwise. This defaults to the safe side —
# an operator must opt into development mode, rather than opt out of
# production protections.
IS_PRODUCTION = os.environ.get("FLASK_ENV", "production").lower() != "development"

# HARDENING FIX (environment): a SECRET_KEY this short/guessable can be
# brute-forced offline to forge session cookies. 32 chars is a practical
# floor for a random token (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`).
MIN_SECRET_KEY_LENGTH = 32


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", INSECURE_DEFAULT_SECRET_KEY)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'csu.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

    # HARDENING FIX (environment): DEBUG must never be on in production —
    # it exposes the Werkzeug interactive debugger (arbitrary code
    # execution) on any unhandled exception. Only ever enabled by
    # explicitly setting FLASK_ENV=development.
    DEBUG = not IS_PRODUCTION

    # HARDENING FIX (environment): session cookie flags.
    # - SECURE:   never send the session cookie over plain HTTP.
    # - HTTPONLY: not readable from JavaScript, blunting XSS-based
    #             session theft.
    # - SAMESITE: default browser CSRF mitigation alongside WTF_CSRF.
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # 1 MB request body cap (FIX 7 — reject oversized payloads outright).
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024

    # FIX 1: which roles may create/edit Knowledge Base articles.
    # Default keeps existing behavior (agent + admin can edit KB).
    # Set ALLOWED_KB_EDITOR_ROLES=admin in the environment to restrict to admins only.
    ALLOWED_KB_EDITOR_ROLES = [
        r.strip()
        for r in os.environ.get("ALLOWED_KB_EDITOR_ROLES", "admin,agent").split(",")
        if r.strip()
    ]

    # Pagination defaults (FIX 4).
    ITEMS_PER_PAGE = int(os.environ.get("ITEMS_PER_PAGE", 10))

    # CHECK 3: default rate limit applied to every route automatically by
    # Flask-Limiter (login gets a stricter override — see auth_routes.py).
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "200 per hour;50 per minute")

    # CHECK 5 fix: explicit, configurable rate limit for the JSON API
    # blueprint (previously the API only had the implicit global default
    # above, which wasn't visible or tested from api_routes.py itself).
    API_RATE_LIMIT = os.environ.get("API_RATE_LIMIT", "60 per minute")


def assert_production_secret_key(app):
    """
    HARDENING FIX (environment): hard-fail startup in production if
    SECRET_KEY is missing, the shipped default, or too short/guessable.
    A weak SECRET_KEY lets an attacker forge session cookies and the
    CSRF token derived from them, so this is treated as a fatal
    misconfiguration rather than a warning once real traffic is possible.

    Deliberately called from run.py (the actual process entrypoint) —
    not from create_app() — so create_app() stays usable as-is for
    tests, `flask db migrate`, seed.py, etc. without every caller having
    to supply a production-grade key.
    """
    if not IS_PRODUCTION:
        return
    key = app.config.get("SECRET_KEY") or ""
    if key == INSECURE_DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "Refusing to start: SECRET_KEY is still the insecure default. "
            "Set a random SECRET_KEY in the environment "
            '(e.g. `python -c "import secrets; print(secrets.token_hex(32))"`).'
        )
    if len(key) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(
            f"Refusing to start: SECRET_KEY is too short ({len(key)} chars, "
            f"minimum {MIN_SECRET_KEY_LENGTH}). Set a long, random SECRET_KEY "
            "in the environment."
        )
