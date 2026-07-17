"""
run.py — application entry point.

Development:
    python run.py

Production (FIX 9) — the module-level `app` object below is a standard
WSGI callable, so Gunicorn can serve it directly without any changes:
    gunicorn -w 4 -b 0.0.0.0:8000 run:app
"""
from app import create_app
from app.config import assert_production_secret_key

app = create_app()

# HARDENING FIX (environment): fail fast at real startup if this process
# is about to serve production traffic with a weak/default SECRET_KEY.
# Kept out of create_app() itself so tests, `flask db` commands, and
# seed.py (which all call create_app() directly) are unaffected.
assert_production_secret_key(app)

if __name__ == "__main__":
    app.run(debug=False)
