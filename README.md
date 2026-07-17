# CSU Knowledge Base + SOP Management System (Production Refactor)

A modular Flask application with SQLAlchemy ORM, Flask-Login authentication,
role-based access control (admin/agent), a JSON API, Flask-Migrate migrations,
pagination, structured validation, centralized logging, standardized error
handling, and security hardening — refactored from the original single-file MVP
and then audited/hardened for production readiness.

## What changed from the MVP
- **Modular app factory** (`app/__init__.py` — `create_app()`), not a single `app.py`.
- **SQLAlchemy ORM** instead of raw `sqlite3`.
- **Authentication** via Flask-Login: `/login`, `/logout`. All pages require login.
- **Roles**: `admin` and `agent`.
  - **Delete** (KB and SOP, web + API) → **admin only**.
  - **SOP create/edit** (web + API) → **admin only**.
  - **KB create/edit** (web + API) → **configurable**, defaults to allowing both
    `admin` and `agent` (set `ALLOWED_KB_EDITOR_ROLES=admin` in `.env` to restrict
    to admins only — see Audit Fix 1).
- **Service layer** (`app/services/`) holds business logic; routes stay thin.
- **JSON API** at `/api/kb` and `/api/sop` (GET/POST/PUT/DELETE), session-authenticated.
- **CSRF protection** (Flask-WTF) on all HTML forms; the JSON API is CSRF-exempt
  (standard for token/session-based JSON APIs) but still requires login.
- **Flask-Migrate** for schema migrations instead of a one-off `init_db.py`.
- **Pagination** on the KB and SOP list views/API endpoints (`ITEMS_PER_PAGE` in `.env`).
- **Structured validation** (`app/validation.py`) — required fields, max lengths,
  and tag-format checks, shared by the web forms and the JSON API.
- **Centralized logging** (`app/logging_config.py`) — auth events, CRUD actions,
  and errors are written to `logs/app.log` (rotating file handler).
- **Standardized error handling** — custom 404/500 pages for the browser, JSON
  errors for `/api/*`, and a DB session rollback on 500s.
- **Security headers** (`X-Frame-Options`, `X-Content-Type-Options`,
  `X-XSS-Protection`) added to every response.
- **Gunicorn-ready** — `run.py` exposes a module-level `app` WSGI callable.
- Original KB/SOP fields (category, problem, solution, purpose, scope, procedure,
  responsible_person) are preserved — see Assumption #1 below.

## Target project structure
```
csu_kb_sop/
├── app/
│   ├── __init__.py         # App factory
│   ├── config.py           # Config from environment
│   ├── extensions.py        # Shared db/migrate/login_manager/csrf instances*
│   ├── decorators.py        # @role_required("admin"), @kb_editor_required*
│   ├── validation.py         # Structured input validation (Audit Fix 2)*
│   ├── logging_config.py     # Central logging + CRUD/auth log helpers (Audit Fix 5)*
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── kb.py
│   │   └── sop.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth_routes.py
│   │   ├── main_routes.py   # home + search*
│   │   ├── kb_routes.py
│   │   ├── sop_routes.py
│   │   └── api_routes.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── kb_service.py
│   │   └── sop_service.py
│   ├── templates/
│   │   ├── errors/           # 404.html, 500.html (Audit Fix 6)*
│   │   └── ...                # login, home, kb_*, sop_*, search, base
│   └── static/               # present but currently empty (CSS is inline in base.html)
├── migrations/               # created by `flask db init` (see setup below)
├── logs/                     # created at runtime by logging_config.py; app.log lives here
├── tests/
│   └── test_basic.py
├── seed.py                   # replaces init_db.py
├── run.py                    # dev server AND Gunicorn WSGI entrypoint
├── requirements.txt
└── .env.example
```
`*` = not explicitly named in the original spec's file tree, added because the
app factory pattern requires them (see Assumptions #3 and #4 below), or because
the production audit fixes needed a home (`validation.py`, `logging_config.py`,
`templates/errors/`).

## Setup Instructions

### 1. Install dependencies
```bash
cd csu_kb_sop
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env and set a real SECRET_KEY, and optionally custom seed passwords,
# ALLOWED_KB_EDITOR_ROLES, and ITEMS_PER_PAGE.
```

### 3. Initialize the database with migrations
```bash
export FLASK_APP=run.py         # Windows (PowerShell): $env:FLASK_APP="run.py"
flask db init                   # creates the migrations/ folder (first time only)
flask db migrate -m "Initial schema"
flask db upgrade                # creates csu.db with the users/knowledge_base/sops tables
```

### 4. Seed initial users and example data
```bash
python seed.py
```
This creates two accounts (override via `.env`):
| Username | Password  | Role  |
|----------|-----------|-------|
| admin    | admin123  | admin |
| agent    | agent123  | agent |

and two example Knowledge Base articles + two example SOPs, matching the
original MVP's seed data.

### 5. Run the app

Development:
```bash
python run.py
```

Production (Audit Fix 9):
```bash
gunicorn -w 4 -b 0.0.0.0:8000 run:app
```
Open `http://127.0.0.1:5000` (dev) or your Gunicorn bind address, and log in
with one of the accounts above.

### 6. Run the test suite
```bash
pip install pytest
pytest
```
Covers login/logout, KB/SOP CRUD, the admin-only SOP and delete rules, the
configurable KB-editor permission, validation errors, pagination, the 404
handler, and the security headers.

## ⚠️ Important note on verification
Both the original refactor and this production-hardening pass were built and
reviewed in a sandbox **without internet access**, so the dependencies
(Flask-SQLAlchemy, Flask-Login, Flask-Migrate, Flask-WTF, pytest, gunicorn)
could not be installed there to run the app, the migrations, or the test suite
live. What *was* verified in that sandbox for this pass:
- Every `.py` file (including the new `validation.py`, `logging_config.py`)
  compiles and parses as valid Python (`py_compile` + `ast.parse`).
- Every Jinja2 template (including the new `errors/404.html`, `errors/500.html`)
  parses with no syntax errors.
- Every `url_for(...)` call in the templates matches an actual
  `blueprint.endpoint` name registered in the route files.
- Decorator stacking order (`@login_required` outer, `@role_required`/
  `@kb_editor_required` inner) was checked on every protected route.
- The route/service/model logic was written and manually traced against the
  same request flows already proven to work pre-refactor.

Please run Steps 1–6 above on your machine (with internet access) to do a
final end-to-end check — in particular confirm that `flask db migrate` detects
all three models correctly and that `pytest` passes. If anything doesn't work
as expected, let me know the exact error and I'll fix it.

## Assumptions made
1. **KB/SOP fields**: the spec's model field lists for `kb.py`/`sop.py` (just
   `content`) would have dropped the original `category/problem/solution` and
   `purpose/scope/procedure/responsible_person` fields. Kept the originals and
   added the new fields (`created_by`, `updated_at` for KB; `version`,
   `is_active`, `created_by` for SOP) on top, per "do not remove existing features."
2. **Delete/SOP roles**: per this audit's explicit rules — delete is admin-only
   everywhere, and SOP create/edit is admin-only everywhere.
3. **`main_routes.py`**: home and search don't belong to auth/kb/sop/api, so
   they got their own small blueprint to keep the split clean.
4. **`extensions.py` / `decorators.py` / `validation.py` / `logging_config.py`**:
   not in the original file tree, but required to avoid circular imports
   (`extensions.py`), implement role checks (`decorators.py`), and give the
   new validation/logging fixes a clean home without bloating routes/services.
5. **API auth**: session-based via Flask-Login (same login as the web UI),
   not a separate token/API-key scheme, to keep the project simple as instructed.
6. **SOP `version`**: increments by 1 on every edit, since the field was
   requested but its update behavior wasn't specified.
7. **Seed accounts**: `admin/admin123` and `agent/agent123` — change these
   immediately if this ever runs somewhere reachable by others.
8. **KB create vs. edit**: "KB edit → configurable" is applied to both KB
   creation and editing (not just editing an existing article), since treating
   "create" as a stricter case than "edit" under the same permission would be
   an inconsistent, hard-to-explain rule.
9. **Validation approach**: implemented as plain Python validation functions
   (`app/validation.py`) rather than full Flask-WTF form classes, so the
   existing plain-HTML templates didn't need to be restructured around
   WTForms field rendering — preserves template compatibility per the audit's
   constraints, while still returning specific, itemized error messages.
10. **DB error handling**: rather than wrapping every service function in its
    own `try/except`, uncaught DB exceptions (e.g. constraint violations) are
    caught once at the top by the global 500 handler (which also rolls back
    the session) — avoids duplicating error-handling boilerplate across every
    CRUD function (Audit Fix 8: clean code).
