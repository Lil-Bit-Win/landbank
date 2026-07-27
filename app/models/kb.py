from datetime import datetime
import uuid

from app.extensions import db


class KnowledgeBase(db.Model):
    __tablename__ = "knowledge_base"

    id = db.Column(db.Integer, primary_key=True)
    # FEATURE 5 (optional, enterprise): opaque external identifier.
    # Additive and non-breaking — `id` (int) keeps working exactly as
    # before on every existing route; `public_id` is simply also exposed
    # for any client that prefers not to expose sequential integers.
    public_id = db.Column(db.String(36), unique=True, nullable=True, default=lambda: str(uuid.uuid4()))
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    problem = db.Column(db.Text, nullable=False)
    solution = db.Column(db.Text, nullable=False)
    tags = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # FEATURE 2 (enterprise): soft delete — hard `DELETE` permanently
    # destroys audit-relevant history, so "deleting" now flags the row
    # instead. Defaults preserve existing behavior for any pre-existing
    # rows (nullable/defaulted, so no backfill migration is required).
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    author = db.relationship("User", foreign_keys=[created_by])

    def to_dict(self):
        return {
            "id": self.id,
            "public_id": self.public_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "problem": self.problem,
            "solution": self.solution,
            "tags": self.tags,
            "created_by": self.created_by,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M") if self.updated_at else None,
        }
