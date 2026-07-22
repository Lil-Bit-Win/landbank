from datetime import datetime

from app.extensions import db, safe_commit
from app.models.sop import SOP
from app.validation import sanitize_text

# Validation of user input now lives in app/validation.py
# (validate_sop_input) — see kb_service.py for the same note.


def list_sop(page=1, per_page=10):
    """
    Returns a Flask-SQLAlchemy Pagination object (FIX 4).

    FEATURE 2 (soft delete): soft-deleted rows excluded by default.
    """
    query = SOP.query.filter_by(is_deleted=False).order_by(SOP.id.desc())
    return query.paginate(page=page, per_page=per_page, error_out=False)


def get_sop(sop_id, include_deleted=False):
    """
    FEATURE 2 (soft delete): see kb_service.get_kb() for the same pattern.
    PATCH (query consistency): single filtered query, same as get_kb().
    """
    if include_deleted:
        return SOP.query.filter_by(id=sop_id).first()
    return SOP.query.filter_by(id=sop_id, is_deleted=False).first()


def create_sop(data, user_id=None):
    sop = SOP(
        title=sanitize_text(data.get("title")),
        description=sanitize_text(data.get("description")),
        purpose=sanitize_text(data.get("purpose")),
        scope=sanitize_text(data.get("scope")),
        procedure=sanitize_text(data.get("procedure")),
        responsible_person=sanitize_text(data.get("responsible_person")),
        created_by=user_id,
    )
    db.session.add(sop)
    safe_commit()
    return sop


def update_sop(sop, data):
    sop.title = sanitize_text(data.get("title"))
    sop.description = sanitize_text(data.get("description"))
    sop.purpose = sanitize_text(data.get("purpose"))
    sop.scope = sanitize_text(data.get("scope"))
    sop.procedure = sanitize_text(data.get("procedure"))
    sop.responsible_person = sanitize_text(data.get("responsible_person"))
    sop.version = (sop.version or 1) + 1
    safe_commit()
    return sop


def delete_sop(sop):
    """FEATURE 2 (soft delete): see kb_service.delete_kb() for rationale."""
    sop.is_deleted = True
    sop.deleted_at = datetime.utcnow()
    safe_commit()


def search_sop(query):
    like = f"%{query}%"
    return (
        SOP.query.filter(
            SOP.is_deleted.is_(False),
            db.or_(
                SOP.title.ilike(like),
                SOP.description.ilike(like),
                SOP.purpose.ilike(like),
                SOP.scope.ilike(like),
                SOP.procedure.ilike(like),
            ),
        )
        .order_by(SOP.id.desc())
        .all()
    )
