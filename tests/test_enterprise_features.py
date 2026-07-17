"""
tests/test_enterprise_features.py

Coverage for the 4 enterprise features added on top of the hardened
baseline:
  1. Audit logging      -> AuditLog rows for auth events, CRUD, and
                            unauthorized-access attempts
  2. Soft delete         -> deleted rows hidden from queries but kept in DB
  3. Permission system   -> permission_required() + has_permission()
  4. Observability       -> log_event() structured logging + in-memory metrics
  5. (optional) UUID     -> public_id exposed and usable for lookups

Run with:
    pytest tests/test_enterprise_features.py -v
"""
import pytest

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.kb import KnowledgeBase
from app.models.audit_log import AuditLog


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

        admin = User(username="entadmin", role="admin")
        admin.set_password("testpass")
        agent = User(username="entagent", role="agent")
        agent.set_password("testpass")
        db.session.add_all([admin, agent])
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


# ---------------------------------------------------------------------
# FEATURE 1 — audit logging
# ---------------------------------------------------------------------
def test_login_writes_audit_log(client, app):
    login(client, "entadmin")
    with app.app_context():
        rows = AuditLog.query.filter_by(action="AUTH_LOGIN").all()
        assert len(rows) == 1
        assert rows[0].event_metadata["username"] == "entadmin"
        assert rows[0].event_metadata["success"] is True


def test_failed_login_writes_audit_log(client, app):
    client.post("/login", data={"username": "entadmin", "password": "wrong"})
    with app.app_context():
        rows = AuditLog.query.filter_by(action="AUTH_LOGIN").all()
        assert len(rows) == 1
        assert rows[0].event_metadata["success"] is False


def test_kb_create_writes_audit_log(client, app):
    login(client, "entadmin")
    resp = client.post(
        "/api/kb", json={"title": "T", "category": "Network", "problem": "p", "solution": "s"}
    )
    article_id = resp.get_json()["data"]["id"]

    with app.app_context():
        row = AuditLog.query.filter_by(action="CREATE_KNOWLEDGEBASE", resource_id=article_id).first()
        assert row is not None
        assert row.resource_type == "KnowledgeBase"
        assert row.event_metadata["username"] == "entadmin"


def test_forbidden_access_writes_audit_log(client, app):
    login(client, "entagent")
    resp = client.post(
        "/api/sop",
        json={"title": "T", "purpose": "p", "scope": "s", "procedure": "proc", "responsible_person": "X"},
    )
    assert resp.status_code == 403

    with app.app_context():
        rows = AuditLog.query.filter_by(action="FORBIDDEN_ACCESS_ATTEMPT").all()
        assert len(rows) >= 1
        assert rows[-1].event_metadata["path"] == "/api/sop"


# ---------------------------------------------------------------------
# FEATURE 2 — soft delete
# ---------------------------------------------------------------------
def test_deleted_kb_hidden_from_list_and_get_but_kept_in_db(client, app):
    login(client, "entadmin")
    resp = client.post(
        "/api/kb", json={"title": "ToSoftDelete", "category": "Network", "problem": "p", "solution": "s"}
    )
    article_id = resp.get_json()["data"]["id"]

    del_resp = client.delete(f"/api/kb/{article_id}")
    assert del_resp.status_code == 200

    # Hidden from the API now (matches old hard-delete behavior)...
    get_resp = client.get(f"/api/kb/{article_id}")
    assert get_resp.status_code == 404

    list_resp = client.get("/api/kb")
    ids = [item["id"] for item in list_resp.get_json()["data"]["items"]]
    assert article_id not in ids

    # ...but the row itself is still in the database, flagged.
    with app.app_context():
        article = KnowledgeBase.query.get(article_id)
        assert article is not None
        assert article.is_deleted is True
        assert article.deleted_at is not None


# ---------------------------------------------------------------------
# FEATURE 3 — permission system
# ---------------------------------------------------------------------
def test_agent_still_blocked_from_sop_create_via_permission_required(client):
    """Behavior parity check: permission_required("create_sop") must
    still block agents exactly as role_required("admin") did before."""
    login(client, "entagent")
    resp = client.post(
        "/api/sop",
        json={"title": "T", "purpose": "p", "scope": "s", "procedure": "proc", "responsible_person": "X"},
    )
    assert resp.status_code == 403


def test_admin_still_allowed_sop_create_via_permission_required(client):
    login(client, "entadmin")
    resp = client.post(
        "/api/sop",
        json={"title": "T", "purpose": "p", "scope": "s", "procedure": "proc", "responsible_person": "X"},
    )
    assert resp.status_code == 201


def test_has_permission_admin_always_true(app):
    from app.services.permission_service import has_permission
    with app.app_context():
        assert has_permission("admin", "anything_not_even_a_real_permission") is True


def test_has_permission_default_fallback_matches_legacy_roles(app):
    from app.services.permission_service import has_permission
    with app.app_context():
        assert has_permission("agent", "delete_kb") is False
        assert has_permission("agent", "edit_kb") is True


def test_custom_role_permission_mapping_overrides_default(app):
    """Once an operator configures a mapping for a permission name, it
    becomes authoritative — proving the system is genuinely DB-driven,
    not just a hardcoded shim."""
    from app.models.permission import Permission, RolePermission
    from app.services.permission_service import has_permission

    with app.app_context():
        perm = Permission(name="delete_kb")
        db.session.add(perm)
        db.session.commit()
        db.session.add(RolePermission(role="agent", permission_id=perm.id))
        db.session.commit()

        # Now explicitly granted to agents, overriding the admin-only default.
        assert has_permission("agent", "delete_kb") is True


def test_ensure_default_permissions_is_idempotent(app):
    from app.services.permission_service import ensure_default_permissions
    from app.models.permission import Permission

    with app.app_context():
        ensure_default_permissions()
        count_after_first = Permission.query.count()
        ensure_default_permissions()
        count_after_second = Permission.query.count()
        assert count_after_first == count_after_second
        assert count_after_first > 0


# ---------------------------------------------------------------------
# FEATURE 4 — observability
# ---------------------------------------------------------------------
def test_metrics_endpoint_tracks_requests(client):
    login(client, "entadmin")
    client.get("/api/kb")
    client.get("/api/kb")

    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["request_count"] > 0
    assert "status_counts" in data
    assert "endpoint_counts" in data


def test_metrics_endpoint_is_admin_only(client):
    login(client, "entagent")
    resp = client.get("/api/metrics")
    assert resp.status_code == 403


def test_log_event_produces_valid_json(app, caplog):
    import logging
    from app.logging_config import log_event

    with app.app_context():
        with caplog.at_level(logging.INFO):
            log_event("test_event", foo="bar", n=1)
        assert any('"event": "test_event"' in r.message for r in caplog.records)


# ---------------------------------------------------------------------
# FEATURE 5 (optional) — UUID / public_id
# ---------------------------------------------------------------------
def test_kb_article_has_public_id_and_int_id_still_works(client):
    """Existing integer-id API must keep working unchanged."""
    login(client, "entadmin")
    resp = client.post(
        "/api/kb", json={"title": "UUID Test", "category": "Network", "problem": "p", "solution": "s"}
    )
    body = resp.get_json()["data"]
    assert "public_id" in body
    assert len(body["public_id"]) == 36  # standard UUID string length

    # The pre-existing integer-id route is untouched.
    get_resp = client.get(f"/api/kb/{body['id']}")
    assert get_resp.status_code == 200


def test_kb_lookup_by_public_id(client):
    login(client, "entadmin")
    resp = client.post(
        "/api/kb", json={"title": "UUID Lookup", "category": "Network", "problem": "p", "solution": "s"}
    )
    public_id = resp.get_json()["data"]["public_id"]

    resp2 = client.get(f"/api/kb/uuid/{public_id}")
    assert resp2.status_code == 200
    assert resp2.get_json()["data"]["title"] == "UUID Lookup"


def test_kb_lookup_by_unknown_public_id_404s(client):
    login(client, "entadmin")
    resp = client.get("/api/kb/uuid/not-a-real-uuid")
    assert resp.status_code == 404
