from datetime import datetime
import uuid

from app.extensions import db


class SOP(db.Model):
    __tablename__ = "sops"

    id = db.Column(db.Integer, primary_key=True)
    # FEATURE 5 (optional, enterprise): opaque external identifier,
    # additive alongside the existing integer `id` — see kb.py for
    # the same pattern and rationale.
    public_id = db.Column(db.String(36), unique=True, nullable=True, default=lambda: str(uuid.uuid4()))
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    purpose = db.Column(db.Text, nullable=False)
    scope = db.Column(db.Text, nullable=False)
    procedure = db.Column(db.Text, nullable=False)
    responsible_person = db.Column(db.String(150), nullable=False)
    version = db.Column(db.Integer, default=1, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # FEATURE 2 (enterprise): soft delete — see kb.py for rationale.
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    author = db.relationship("User", foreign_keys=[created_by])

    def to_dict(self):
        return {
            "id": self.id,
            "public_id": self.public_id,
            "title": self.title,
            "description":self.description,
            "purpose": self.purpose,
            "scope": self.scope,
            "procedure": self.procedure,
            "responsible_person": self.responsible_person,
            "version": self.version,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
        }
