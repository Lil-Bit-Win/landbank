from datetime import datetime

from app.extensions import db, safe_commit
from app.models.kb import KnowledgeBase
from app.validation import sanitize_text

# Validation of user input now lives in app/validation.py
# (validate_kb_input) — it returns a list of specific error messages
# instead of the old boolean-only check, and is shared by both the web
# routes and the JSON API.


def list_kb(category=None, page=1, per_page=10):
    """
    Returns a Flask-SQLAlchemy Pagination object (FIX 4).
    Callers use `.items` for the current page's rows and the other
    attributes (page, pages, has_next, has_prev, total) for nav controls.

    FEATURE 2 (soft delete): soft-deleted rows are excluded by default,
    matching the previous (hard-delete) behavior where a deleted row
    simply could not appear here.
    """
    query = KnowledgeBase.query.filter_by(is_deleted=False)
    if category:
        query = query.filter_by(category=category)
    query = query.order_by(KnowledgeBase.id.desc())
    return query.paginate(page=page, per_page=per_page, error_out=False)


def get_kb(article_id, include_deleted=False):
    """
    FEATURE 2 (soft delete): excludes soft-deleted rows by default, so a
    "deleted" article 404s exactly as it did under hard delete. Pass
    include_deleted=True for internal/admin tooling that needs to see it
    anyway (e.g. a future "restore" feature).

    PATCH (query consistency): collapsed to a single filtered query
    (`filter_by(id=..., is_deleted=False)`) for the common case instead
    of `.get()` + a manual attribute check — same verified behavior
    (already covered by tests: double-delete -> 404, update-on-deleted
    -> 404), just one query expression instead of two steps.
    """
    if include_deleted:
        return KnowledgeBase.query.filter_by(id=article_id).first()
    return KnowledgeBase.query.filter_by(id=article_id, is_deleted=False).first()


def create_kb(data, user_id=None):
    article = KnowledgeBase(
        title=sanitize_text(data.get("title")),
        category=sanitize_text(data.get("category")),
        problem=sanitize_text(data.get("problem")),
        solution=sanitize_text(data.get("solution")),
        tags=sanitize_text(data.get("tags")),
        created_by=user_id,
    )
    db.session.add(article)
    safe_commit()
    return article


def update_kb(article, data):
    article.title = sanitize_text(data.get("title"))
    article.category = sanitize_text(data.get("category"))
    article.problem = sanitize_text(data.get("problem"))
    article.solution = sanitize_text(data.get("solution"))
    article.tags = sanitize_text(data.get("tags"))
    article.updated_at = datetime.utcnow()
    safe_commit()
    return article


def delete_kb(article):
    """
    FEATURE 2 (soft delete): flips is_deleted/deleted_at instead of
    issuing a hard DELETE, so the row (and its audit-log history) is
    preserved. list_kb()/get_kb() already filter it out, so from the
    caller's point of view the article "disappears" exactly as before.
    """
    article.is_deleted = True
    article.deleted_at = datetime.utcnow()
    safe_commit()


def search_kb(query):
    like = f"%{query}%"
    return (
        KnowledgeBase.query.filter(
            KnowledgeBase.is_deleted.is_(False),
            db.or_(
                KnowledgeBase.title.ilike(like),
                KnowledgeBase.problem.ilike(like),
                KnowledgeBase.solution.ilike(like),
                KnowledgeBase.tags.ilike(like),
            ),
        )
        .order_by(KnowledgeBase.id.desc())
        .all()
    )
