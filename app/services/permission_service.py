"""
FEATURE 3 (enterprise): permission-check service, following the same
plain-function pattern as kb_service.py / sop_service.py.

Design note (why the fallback exists): this app has no automatic
migration-time data seeding, and create_app() is also called by tests,
`flask db migrate`, and seed.py against databases that may not have the
`permissions`/`role_permissions` tables populated (or even created) yet.
To keep this feature purely additive and never break an un-seeded
deployment, `has_permission()`:

  1. Admins always have every permission (matches existing role_required
     semantics — unchanged behavior for admins).
  2. If an operator HAS configured a RolePermission mapping for a given
     permission name (via ensure_default_permissions() or manually),
     that mapping is authoritative for non-admin roles.
  3. If nothing has been configured yet for that permission name, fall
     back to DEFAULT_PERMISSIONS below — which simply mirrors this app's
     existing pre-RBAC+ behavior, so unseeded installs behave exactly as
     they did before this feature existed.
"""
from app.extensions import db

# Mirrors current, pre-existing role gates exactly (role_required("admin")
# on SOP writes/KB delete). Used only when no explicit DB mapping exists
# yet for a given permission name.
DEFAULT_PERMISSIONS = {
    "view_kb": ["admin", "agent"],
    "edit_kb": ["admin", "agent"],
    "delete_kb": ["admin"],
    "view_sop": ["admin", "agent"],
    "create_sop": ["admin"],
    "edit_sop": ["admin"],
    "delete_sop": ["admin"],
}

# All permission names known to the system — used by ensure_default_permissions().
ALL_PERMISSIONS = list(DEFAULT_PERMISSIONS.keys())


def has_permission(role, permission_name):
    """Returns True/False. Admins always pass."""
    if role == "admin":
        return True

    from app.models.permission import Permission, RolePermission

    grants = (
        RolePermission.query.join(Permission)
        .filter(Permission.name == permission_name)
        .all()
    )
    if grants:
        # A mapping has been explicitly configured for this permission —
        # it is authoritative; the hardcoded default no longer applies.
        return any(g.role == role for g in grants)

    return role in DEFAULT_PERMISSIONS.get(permission_name, [])


def ensure_default_permissions():
    """
    Idempotently creates Permission rows + the DEFAULT_PERMISSIONS
    RolePermission mappings. Safe to call multiple times (e.g. once per
    deployment via seed.py, or once per test fixture) — existing rows
    are left untouched.

    Deliberately NOT called automatically inside create_app(): the
    `permissions`/`role_permissions` tables may not exist yet at that
    point (e.g. before the first `flask db upgrade`), and create_app()
    is also used by tooling that shouldn't require a live DB.
    """
    from app.models.permission import Permission, RolePermission

    for name in ALL_PERMISSIONS:
        if not Permission.query.filter_by(name=name).first():
            db.session.add(Permission(name=name))
    db.session.commit()

    for name, roles in DEFAULT_PERMISSIONS.items():
        permission = Permission.query.filter_by(name=name).first()
        for role in roles:
            exists = RolePermission.query.filter_by(role=role, permission_id=permission.id).first()
            if not exists:
                db.session.add(RolePermission(role=role, permission_id=permission.id))
    db.session.commit()
