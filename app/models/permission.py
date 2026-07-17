from app.extensions import db


class Permission(db.Model):
    """
    FEATURE 3 (enterprise): a named, fine-grained capability (e.g.
    "edit_kb", "delete_sop") — finer-grained than the existing coarse
    `User.role` ("admin"/"agent"), which is left untouched.
    """
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class RolePermission(db.Model):
    """
    Maps an existing `User.role` string to a `Permission`. Deliberately
    keyed on the role *string* rather than a FK to a new "Role" table —
    this stays additive: it extends the existing two roles instead of
    replacing them with a new roles table.
    """
    __tablename__ = "role_permissions"
    __table_args__ = (
        db.UniqueConstraint("role", "permission_id", name="uq_role_permission"),
    )

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey("permissions.id"), nullable=False)

    permission = db.relationship("Permission")

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "permission": self.permission.name if self.permission else None,
        }
