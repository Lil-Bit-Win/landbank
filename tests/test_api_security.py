"""
tests/test_api_security.py

Dedicated API-security test file (CHECK 6). tests/test_basic.py already
covers a lot of this incidentally, but this file exists specifically so
API security guarantees are proven in one place, including the CHECK 5
rate-limiting fix which had no test coverage before this patch.

Run with:
    pytest tests/test_api_security.py -v
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
        WTF_CSRF_ENABLED=False,
    )
    with flask_app.app_context():
        db.create_all()
        admin = User(username="secadmin", role="admin")
        admin.set_password("testpass")
        agent = User(username="secagent", role="agent")
        agent.set_password("testpass")
        db.session.add_all([admin, agent])
        db.session.commit()
    yield flask_app

    # TEST HARDENING FIX: see tests/test_basic.py — without dropping
    # tables here, the shared sqlite ":memory:" engine leaks rows into
    # the next test that reuses this fixture.
    with flask_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username, password):
    return client.post("/login", data={"username": username, "password": password})


# ---------------------------------------------------------------------
# Unauthorized access blocked (every API endpoint, every method)
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/kb"),
        ("post", "/api/kb"),
        ("get", "/api/kb/1"),
        ("put", "/api/kb/1"),
        ("delete", "/api/kb/1"),
        ("get", "/api/sop"),
        ("post", "/api/sop"),
        ("get", "/api/sop/1"),
        ("put", "/api/sop/1"),
        ("delete", "/api/sop/1"),
    ],
)
def test_all_api_endpoints_require_login(client, method, path):
    resp = getattr(client, method)(path, json={})
    assert resp.status_code == 401
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"] == "Authentication required"


# ---------------------------------------------------------------------
# Invalid payload rejected
# ---------------------------------------------------------------------
def test_kb_create_rejects_empty_payload(client):
    login(client, "secadmin", "testpass")
    resp = client.post("/api/kb", json={})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False
    assert isinstance(body["error"], list)
    assert len(body["error"]) > 0


def test_sop_create_rejects_empty_payload(client):
    login(client, "secadmin", "testpass")
    resp = client.post("/api/sop", json={})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_kb_update_rejects_invalid_payload(client):
    login(client, "secadmin", "testpass")
    create_resp = client.post(
        "/api/kb",
        json={"title": "T", "category": "Network", "problem": "p", "solution": "s"},
    )
    article_id = create_resp.get_json()["data"]["id"]

    resp = client.put(f"/api/kb/{article_id}", json={"title": ""})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


# ---------------------------------------------------------------------
# Role enforcement
# ---------------------------------------------------------------------
def test_agent_forbidden_from_sop_write_endpoints(client):
    login(client, "secagent", "testpass")
    resp = client.post(
        "/api/sop",
        json={"title": "T", "purpose": "p", "scope": "s", "procedure": "proc", "responsible_person": "X"},
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["success"] is False
    assert "Forbidden" in body["error"]


def test_agent_forbidden_from_kb_delete(client):
    login(client, "secadmin", "testpass")
    create_resp = client.post(
        "/api/kb", json={"title": "T", "category": "Network", "problem": "p", "solution": "s"}
    )
    article_id = create_resp.get_json()["data"]["id"]
    client.get("/logout")

    login(client, "secagent", "testpass")
    resp = client.delete(f"/api/kb/{article_id}")
    assert resp.status_code == 403


def test_kb_editor_role_configurable_blocks_agent(client, app):
    app.config["ALLOWED_KB_EDITOR_ROLES"] = ["admin"]
    login(client, "secagent", "testpass")
    resp = client.post(
        "/api/kb", json={"title": "T", "category": "Network", "problem": "p", "solution": "s"}
    )
    assert resp.status_code == 403


def test_admin_allowed_everywhere(client):
    login(client, "secadmin", "testpass")
    resp = client.post(
        "/api/sop",
        json={"title": "T", "purpose": "p", "scope": "s", "procedure": "proc", "responsible_person": "X"},
    )
    assert resp.status_code == 201
    sop_id = resp.get_json()["data"]["id"]
    resp = client.delete(f"/api/sop/{sop_id}")
    assert resp.status_code == 200


# ---------------------------------------------------------------------
# CHECK 5 fix: explicit API rate limiting (previously untested/implicit)
# ---------------------------------------------------------------------
def test_api_rate_limit_enforced(client, app):
    app.config["API_RATE_LIMIT"] = "2 per minute"
    login(client, "secadmin", "testpass")

    r1 = client.get("/api/kb")
    r2 = client.get("/api/kb")
    r3 = client.get("/api/kb")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    body = r3.get_json()
    assert body["success"] is False
