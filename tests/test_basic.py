"""
Minimal smoke tests covering login, CRUD, and role restrictions.
Run with:
    pytest
"""
import pytest

from app import create_app
from app.extensions import db
from app.models.user import User


@pytest.fixture
def app():
    flask_app = create_app()
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,  # simplifies posting form data in tests
    )
    with flask_app.app_context():
        db.create_all()

        admin = User(username="testadmin", role="admin")
        admin.set_password("testpass")
        agent = User(username="testagent", role="agent")
        agent.set_password("testpass")
        db.session.add_all([admin, agent])
        db.session.commit()

    yield flask_app

    # TEST HARDENING FIX: the sqlite ":memory:" engine can outlive this
    # single create_app() call (it's bound to the shared `db` extension
    # instance), so without an explicit drop here, rows created by this
    # test were leaking into the next test's "fresh" db.create_all() and
    # causing spurious UNIQUE-constraint failures.
    with flask_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username, password):
    return client.post(
        "/login", data={"username": username, "password": password}, follow_redirects=True
    )


def test_home_requires_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_login_success_and_home(client):
    resp = login(client, "testadmin", "testpass")
    assert resp.status_code == 200
    resp = client.get("/")
    assert resp.status_code == 200


def test_login_failure(client):
    resp = login(client, "testadmin", "wrongpass")
    assert b"Invalid username or password" in resp.data


def test_kb_create_view_edit(client):
    login(client, "testadmin", "testpass")

    resp = client.post(
        "/kb/new",
        data={
            "title": "Test Article",
            "category": "Network",
            "problem": "p",
            "solution": "s",
            "tags": "t",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Test Article" in resp.data

    resp = client.get("/kb")
    assert b"Test Article" in resp.data


def test_agent_cannot_delete_kb(client):
    login(client, "testadmin", "testpass")
    client.post(
        "/kb/new",
        data={"title": "ToDelete", "category": "Network", "problem": "p", "solution": "s", "tags": ""},
        follow_redirects=True,
    )
    client.get("/logout")

    login(client, "testagent", "testpass")
    resp = client.post("/kb/1/delete", follow_redirects=False)
    assert resp.status_code == 403


def test_admin_can_delete_kb(client):
    login(client, "testadmin", "testpass")
    client.post(
        "/kb/new",
        data={"title": "ToDelete2", "category": "Network", "problem": "p", "solution": "s", "tags": ""},
        follow_redirects=True,
    )
    resp = client.post("/kb/1/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"ToDelete2" not in resp.data


def test_api_requires_login(client):
    resp = client.get("/api/kb")
    assert resp.status_code == 401
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"] == "Authentication required"


def test_api_kb_crud(client):
    login(client, "testadmin", "testpass")

    resp = client.post(
        "/api/kb",
        json={"title": "API Article", "category": "ISP", "problem": "p", "solution": "s", "tags": "x"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["success"] is True
    assert body["error"] is None
    article_id = body["data"]["id"]

    resp = client.get(f"/api/kb/{article_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["title"] == "API Article"

    resp = client.put(f"/api/kb/{article_id}", json={"title": "Updated", "category": "ISP", "problem": "p", "solution": "s"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["title"] == "Updated"

    resp = client.delete(f"/api/kb/{article_id}")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


# --- FIX 1: role rules -------------------------------------------------
def test_agent_can_create_and_edit_kb_by_default(client):
    login(client, "testagent", "testpass")
    resp = client.post(
        "/kb/new",
        data={"title": "Agent KB", "category": "Network", "problem": "p", "solution": "s", "tags": ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Agent KB" in resp.data


def test_agent_cannot_create_sop(client):
    login(client, "testagent", "testpass")
    resp = client.post(
        "/sop/new",
        data={
            "title": "Agent SOP", "purpose": "p", "scope": "s",
            "procedure": "proc", "responsible_person": "Someone",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_admin_can_create_sop(client):
    login(client, "testadmin", "testpass")
    resp = client.post(
        "/sop/new",
        data={
            "title": "Admin SOP", "purpose": "p", "scope": "s",
            "procedure": "proc", "responsible_person": "Someone",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Admin SOP" in resp.data


def test_kb_edit_configurable_to_admin_only(app, client):
    app.config["ALLOWED_KB_EDITOR_ROLES"] = ["admin"]
    login(client, "testagent", "testpass")
    resp = client.post(
        "/kb/new",
        data={"title": "Blocked KB", "category": "Network", "problem": "p", "solution": "s", "tags": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 403


# --- FIX 2: structured validation ---------------------------------------
def test_kb_validation_rejects_overlong_title(client):
    login(client, "testadmin", "testpass")
    resp = client.post(
        "/kb/new",
        data={"title": "x" * 201, "category": "Network", "problem": "p", "solution": "s", "tags": ""},
        follow_redirects=True,
    )
    assert b"must be 200 characters or fewer" in resp.data


def test_kb_validation_rejects_bad_tag_format(client):
    login(client, "testadmin", "testpass")
    resp = client.post(
        "/kb/new",
        data={"title": "T", "category": "Network", "problem": "p", "solution": "s", "tags": "bad;tag!"},
        follow_redirects=True,
    )
    assert b"is invalid" in resp.data


# --- FIX 4: pagination ----------------------------------------------------
def test_kb_list_pagination(app, client):
    app.config["ITEMS_PER_PAGE"] = 2
    login(client, "testadmin", "testpass")
    for i in range(5):
        client.post(
            "/kb/new",
            data={"title": f"Item {i}", "category": "Network", "problem": "p", "solution": "s", "tags": ""},
            follow_redirects=True,
        )
    resp = client.get("/kb?page=1")
    assert resp.status_code == 200
    assert b"Page 1 of 3" in resp.data


# --- FIX 6: error handling ------------------------------------------------
def test_404_page(client):
    login(client, "testadmin", "testpass")
    resp = client.get("/kb/9999")  # not-found redirect, still valid page
    assert resp.status_code == 200  # kb_view handles missing id with a flash+redirect, not a raw 404

    resp = client.get("/this-route-does-not-exist")
    assert resp.status_code == 404


# --- PATCH: browser-facing 403 page (previously missing — fell through to
# Flask's default unstyled error page; app/__init__.py now registers a
# handler that renders errors/403.html instead) --------------------------
def test_403_page_rendered_for_browser(client):
    login(client, "testagent", "testpass")
    resp = client.get("/sop/new")  # SOP create is admin-only
    assert resp.status_code == 403
    assert b"Access Denied" in resp.data


# --- FIX 7: security headers -----------------------------------------------
def test_security_headers_present(client):
    resp = client.get("/login")
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-XSS-Protection") == "1; mode=block"


# --- CHECK 2/5: API write routes require login (not just GET) --------------
def test_api_kb_create_requires_login(client):
    resp = client.post("/api/kb", json={"title": "X", "category": "Network", "problem": "p", "solution": "s"})
    assert resp.status_code == 401
    assert resp.get_json()["success"] is False


def test_api_kb_update_requires_login(client):
    resp = client.put("/api/kb/1", json={"title": "X"})
    assert resp.status_code == 401


def test_api_kb_delete_requires_login(client):
    resp = client.delete("/api/kb/1")
    assert resp.status_code == 401


def test_api_sop_create_requires_login(client):
    resp = client.post("/api/sop", json={"title": "X"})
    assert resp.status_code == 401


# --- CHECK 2/5: API role violations -----------------------------------------
def test_api_agent_cannot_create_sop(client):
    login(client, "testagent", "testpass")
    resp = client.post(
        "/api/sop",
        json={"title": "T", "purpose": "p", "scope": "s", "procedure": "proc", "responsible_person": "X"},
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["success"] is False
    assert "Forbidden" in body["error"]


def test_api_agent_cannot_delete_kb(client):
    login(client, "testadmin", "testpass")
    create_resp = client.post(
        "/api/kb", json={"title": "ToDelete", "category": "Network", "problem": "p", "solution": "s"}
    )
    article_id = create_resp.get_json()["data"]["id"]
    client.get("/logout")

    login(client, "testagent", "testpass")
    resp = client.delete(f"/api/kb/{article_id}")
    assert resp.status_code == 403


def test_api_kb_edit_configurable_to_admin_only(app, client):
    app.config["ALLOWED_KB_EDITOR_ROLES"] = ["admin"]
    login(client, "testagent", "testpass")
    resp = client.post("/api/kb", json={"title": "X", "category": "Network", "problem": "p", "solution": "s"})
    assert resp.status_code == 403


# --- CHECK 4/5: invalid payloads return 400 with the standard envelope -----
def test_api_kb_create_invalid_payload(client):
    login(client, "testadmin", "testpass")
    resp = client.post("/api/kb", json={"title": ""})  # missing everything required
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False
    assert body["data"] is None
    assert isinstance(body["error"], list)
    assert any("required" in msg for msg in body["error"])


def test_api_sop_create_invalid_payload(client):
    login(client, "testadmin", "testpass")
    resp = client.post("/api/sop", json={})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_api_kb_get_not_found(client):
    login(client, "testadmin", "testpass")
    resp = client.get("/api/kb/99999")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"] == "Not found"


# --- CHECK 3: rate limiting on login -----------------------------------------
def test_login_rate_limited_after_repeated_attempts(client):
    """
    5 attempts/minute is the configured limit on /login (see auth_routes.py).
    The 6th request in the same window should be rejected with 429.
    Requires Flask-Limiter's real in-memory storage to be active, so this
    exercises the actual limiter rather than mocking it.
    """
    for _ in range(5):
        client.post("/login", data={"username": "testadmin", "password": "wrongpass"})
    resp = client.post("/login", data={"username": "testadmin", "password": "wrongpass"})
    assert resp.status_code == 429
