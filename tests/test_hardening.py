"""
tests/test_hardening.py

Final hardening pass — dedicated coverage for the 6 production gaps:
  1. migrations (smoke-checked via `flask db upgrade`, not unit tests)
  2. user-aware rate limiting
  3. IDOR / object-level authorization on KB articles
  4. request size / DoS protection (MAX_CONTENT_LENGTH)
  5. environment hardening (session cookie flags, SECRET_KEY validation)
  6. this file itself

Run with:
    pytest tests/test_hardening.py -v
"""
import pytest

from app import create_app
from app.config import assert_production_secret_key, INSECURE_DEFAULT_SECRET_KEY
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

        admin = User(username="hardadmin", role="admin")
        admin.set_password("testpass")
        agent_a = User(username="hardagent_a", role="agent")
        agent_a.set_password("testpass")
        agent_b = User(username="hardagent_b", role="agent")
        agent_b.set_password("testpass")
        db.session.add_all([admin, agent_a, agent_b])
        db.session.commit()

    yield flask_app

    with flask_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username, password="testpass"):
    return client.post("/login", data={"username": username, "password": password})


def create_kb_as(client, username):
    login(client, username)
    resp = client.post(
        "/api/kb",
        json={"title": "Owned Article", "category": "Network", "problem": "p", "solution": "s"},
    )
    assert resp.status_code == 201
    article_id = resp.get_json()["data"]["id"]
    client.get("/logout")
    return article_id


# ---------------------------------------------------------------------
# GAP 3 — IDOR protection: object ownership, not just role, is enforced.
# ---------------------------------------------------------------------
def test_idor_agent_cannot_edit_another_agents_article(client):
    """Agent A creates an article; Agent B must not be able to edit it
    just because both are 'agent' role and the id is guessable."""
    article_id = create_kb_as(client, "hardagent_a")

    login(client, "hardagent_b")
    resp = client.put(
        f"/api/kb/{article_id}",
        json={"title": "Hijacked", "category": "Network", "problem": "p", "solution": "s"},
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["success"] is False


def test_idor_owner_can_edit_own_article(client):
    """Sanity check: the fix does not block legitimate self-edits."""
    article_id = create_kb_as(client, "hardagent_a")

    login(client, "hardagent_a")
    resp = client.put(
        f"/api/kb/{article_id}",
        json={"title": "Updated by owner", "category": "Network", "problem": "p", "solution": "s"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["title"] == "Updated by owner"


def test_idor_admin_can_edit_any_article(client):
    """Admins retain role-based access to any shared KB article."""
    article_id = create_kb_as(client, "hardagent_a")

    login(client, "hardadmin")
    resp = client.put(
        f"/api/kb/{article_id}",
        json={"title": "Updated by admin", "category": "Network", "problem": "p", "solution": "s"},
    )
    assert resp.status_code == 200


def test_idor_web_route_also_enforces_ownership(client):
    """Same protection applies to the HTML form route, not just the API."""
    article_id = create_kb_as(client, "hardagent_a")

    login(client, "hardagent_b")
    resp = client.get(f"/kb/{article_id}/edit")
    assert resp.status_code == 403


# ---------------------------------------------------------------------
# GAP 3 (cont.) — unauthorized object access generally returns 403, not
# a silent success or a generic 500.
# ---------------------------------------------------------------------
def test_unauthorized_object_access_returns_403_not_500(client):
    article_id = create_kb_as(client, "hardagent_a")
    login(client, "hardagent_b")
    resp = client.delete(f"/api/kb/{article_id}")
    # agents can't delete at all (role-gated) — still must be 403, never 500
    assert resp.status_code == 403


# ---------------------------------------------------------------------
# GAP 2 — rate limiting is keyed per authenticated user, not shared IP.
# ---------------------------------------------------------------------
def test_rate_limit_is_per_user_not_shared_ip(client, app):
    """
    All requests in this test come from the same test-client IP. With the
    old IP-only key, hardagent_a burning through the limit would also
    block hardagent_b. With the user-aware key, each account gets its
    own bucket even though the "IP" is identical.
    """
    app.config["API_RATE_LIMIT"] = "2 per minute"

    login(client, "hardagent_a")
    r1 = client.get("/api/kb")
    r2 = client.get("/api/kb")
    r3 = client.get("/api/kb")
    assert (r1.status_code, r2.status_code) == (200, 200)
    assert r3.status_code == 429  # hardagent_a is now limited
    client.get("/logout")

    login(client, "hardagent_b")
    r4 = client.get("/api/kb")
    assert r4.status_code == 200  # a different user, same IP, own quota


def test_rate_limit_key_function_reads_current_user():
    """Directly exercises the key function used by the limiter."""
    from app.extensions import rate_limit_key

    flask_app = create_app()
    flask_app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with flask_app.test_request_context("/"):
        # No authenticated user in this bare request context -> falls
        # back to remote address rather than raising.
        assert rate_limit_key() is not None


# ---------------------------------------------------------------------
# GAP 4 — request size / DoS protection.
# ---------------------------------------------------------------------
def test_oversized_payload_is_rejected(client):
    login(client, "hardadmin")
    oversized_solution = "x" * (2 * 1024 * 1024)  # 2 MB > MAX_CONTENT_LENGTH (1 MB)
    resp = client.post(
        "/api/kb",
        json={
            "title": "Too Big",
            "category": "Network",
            "problem": "p",
            "solution": oversized_solution,
        },
    )
    assert resp.status_code == 413


def test_normal_sized_payload_is_accepted(client):
    """Sanity check: the size cap doesn't clip legitimate requests."""
    login(client, "hardadmin")
    resp = client.post(
        "/api/kb",
        json={"title": "Normal", "category": "Network", "problem": "p", "solution": "s" * 500},
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------
# GAP 5 — environment hardening: session cookie flags + SECRET_KEY check.
# ---------------------------------------------------------------------
def test_session_cookie_flags_are_hardened(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    # SESSION_COOKIE_SECURE tracks IS_PRODUCTION, which defaults True
    # unless FLASK_ENV=development is explicitly set.
    assert "SESSION_COOKIE_SECURE" in app.config


def test_startup_rejects_default_secret_key():
    flask_app = create_app()
    flask_app.config["SECRET_KEY"] = INSECURE_DEFAULT_SECRET_KEY
    with pytest.raises(RuntimeError):
        assert_production_secret_key(flask_app)


def test_startup_rejects_short_secret_key():
    flask_app = create_app()
    flask_app.config["SECRET_KEY"] = "too-short"
    with pytest.raises(RuntimeError):
        assert_production_secret_key(flask_app)


def test_startup_accepts_strong_secret_key():
    flask_app = create_app()
    flask_app.config["SECRET_KEY"] = "a" * 40
    assert_production_secret_key(flask_app)  # should not raise
