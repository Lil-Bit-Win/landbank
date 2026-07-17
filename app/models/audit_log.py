from datetime import datetime

from app.extensions import db


class AuditLog(db.Model):
    """
    FEATURE 1 (enterprise): persistent audit trail, distinct from the
    rotating text log file — survives log rotation, is queryable, and
    captures a structured metadata blob per event.

    Note: the column is exposed to the DB as `metadata` (per spec), but
    the Python attribute is named `event_metadata` because `metadata` is
    reserved on `db.Model` for SQLAlchemy's own MetaData object — using
    it directly would raise `InvalidRequestError` at class-definition
    time.
    """
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    # Intentionally NOT a ForeignKey: audit rows must survive even if the
    # referenced user is later hard-deleted (users aren't soft-deleted in
    # this patch), so a log entry is never lost to a FK constraint.
    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50))
    resource_id = db.Column(db.Integer)
    event_metadata = db.Column("metadata", db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "metadata": self.event_metadata,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
