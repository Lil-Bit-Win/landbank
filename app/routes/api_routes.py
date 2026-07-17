from flask import Blueprint, request, current_app
from flask_login import login_required, current_user

from app.services import kb_service, sop_service
from app.decorators import role_required, kb_editor_required, check_kb_ownership, permission_required
from app.validation import validate_kb_input, validate_sop_input
from app.logging_config import log_crud
from app.api_utils import api_success, api_error
from app.extensions import limiter

api_bp = Blueprint("api", __name__, url_prefix="/api")

# CHECK 5 fix: the API previously relied only on the implicit global
# RATELIMIT_DEFAULT — invisible from this file and untested. Make it
# explicit here. Uses a callable so the limit is read from app.config at
# request time (lets tests override API_RATE_LIMIT without rebuilding
# the blueprint).
limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "60 per minute"))(api_bp)


def _pagination_meta(pagination):
    return {
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }


# ---------------------------------------------------------------------------
# Knowledge Base API
# ---------------------------------------------------------------------------
@api_bp.route("/kb", methods=["GET"])
@login_required
def api_kb_list():
    category = request.args.get("category")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", current_app.config.get("ITEMS_PER_PAGE", 10), type=int)
    pagination = kb_service.list_kb(category, page=page, per_page=per_page)
    return api_success({
        "items": [a.to_dict() for a in pagination.items],
        "meta": _pagination_meta(pagination),
    })


@api_bp.route("/kb", methods=["POST"])
@login_required
@kb_editor_required
def api_kb_create():
    data = request.get_json(silent=True) or {}
    errors = validate_kb_input(data)
    if errors:
        return api_error(errors, status_code=400)
    article = kb_service.create_kb(data, user_id=current_user.id)
    log_crud("CREATE", "KnowledgeBase", article.id, current_user.username)
    return api_success(article.to_dict(), status_code=201)


@api_bp.route("/kb/<int:article_id>", methods=["GET"])
@login_required
def api_kb_get(article_id):
    article = kb_service.get_kb(article_id)
    if article is None:
        return api_error("Not found", status_code=404)
    return api_success(article.to_dict())


@api_bp.route("/kb/<int:article_id>", methods=["PUT"])
@login_required
@kb_editor_required
def api_kb_update(article_id):
    article = kb_service.get_kb(article_id)
    if article is None:
        return api_error("Not found", status_code=404)

    # IDOR fix: kb_editor_required only checks the caller's role, not
    # whether *this* article belongs to them — without this, any agent
    # could edit any other agent's article just by guessing article_id.
    denied = check_kb_ownership(article)
    if denied is not None:
        return denied

    data = request.get_json(silent=True) or {}
    errors = validate_kb_input(data)
    if errors:
        return api_error(errors, status_code=400)
    article = kb_service.update_kb(article, data)
    log_crud("UPDATE", "KnowledgeBase", article.id, current_user.username)
    return api_success(article.to_dict())


@api_bp.route("/kb/<int:article_id>", methods=["DELETE"])
@login_required
@permission_required("delete_kb")
def api_kb_delete(article_id):
    article = kb_service.get_kb(article_id)
    if article is None:
        return api_error("Not found", status_code=404)
    # AUDIT FIX: log AFTER the mutation succeeds, not before — logging
    # first would record a false "DELETE" event even if delete_kb() then
    # raised (e.g. a DB error), since safe_commit() re-raises on failure.
    kb_service.delete_kb(article)
    log_crud("DELETE", "KnowledgeBase", article.id, current_user.username)
    return api_success({"deleted": True, "id": article_id})


# ---------------------------------------------------------------------------
# SOP API
# ---------------------------------------------------------------------------
@api_bp.route("/sop", methods=["GET"])
@login_required
def api_sop_list():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", current_app.config.get("ITEMS_PER_PAGE", 10), type=int)
    pagination = sop_service.list_sop(page=page, per_page=per_page)
    return api_success({
        "items": [s.to_dict() for s in pagination.items],
        "meta": _pagination_meta(pagination),
    })


@api_bp.route("/sop", methods=["POST"])
@login_required
@permission_required("create_sop")
def api_sop_create():
    data = request.get_json(silent=True) or {}
    errors = validate_sop_input(data)
    if errors:
        return api_error(errors, status_code=400)
    sop = sop_service.create_sop(data, user_id=current_user.id)
    log_crud("CREATE", "SOP", sop.id, current_user.username)
    return api_success(sop.to_dict(), status_code=201)


@api_bp.route("/sop/<int:sop_id>", methods=["GET"])
@login_required
def api_sop_get(sop_id):
    sop = sop_service.get_sop(sop_id)
    if sop is None:
        return api_error("Not found", status_code=404)
    return api_success(sop.to_dict())


@api_bp.route("/sop/<int:sop_id>", methods=["PUT"])
@login_required
@permission_required("edit_sop")
def api_sop_update(sop_id):
    sop = sop_service.get_sop(sop_id)
    if sop is None:
        return api_error("Not found", status_code=404)
    data = request.get_json(silent=True) or {}
    errors = validate_sop_input(data)
    if errors:
        return api_error(errors, status_code=400)
    sop = sop_service.update_sop(sop, data)
    log_crud("UPDATE", "SOP", sop.id, current_user.username)
    return api_success(sop.to_dict())


@api_bp.route("/sop/<int:sop_id>", methods=["DELETE"])
@login_required
@permission_required("delete_sop")
def api_sop_delete(sop_id):
    sop = sop_service.get_sop(sop_id)
    if sop is None:
        return api_error("Not found", status_code=404)
    sop_service.delete_sop(sop)
    log_crud("DELETE", "SOP", sop.id, current_user.username)
    return api_success({"deleted": True, "id": sop_id})


# ---------------------------------------------------------------------------
# FEATURE 5 (optional, enterprise): lookup by opaque public_id.
# Purely additive — the existing /api/kb/<int:article_id> route above is
# completely unchanged, so no existing client breaks. This just gives
# clients that don't want to expose sequential integer ids an
# equivalent read.
# ---------------------------------------------------------------------------
@api_bp.route("/kb/uuid/<string:public_id>", methods=["GET"])
@login_required
def api_kb_get_by_uuid(public_id):
    from app.models.kb import KnowledgeBase

    article = KnowledgeBase.query.filter_by(public_id=public_id, is_deleted=False).first()
    if article is None:
        return api_error("Not found", status_code=404)
    return api_success(article.to_dict())


# ---------------------------------------------------------------------------
# FEATURE 4 (observability): lightweight in-memory request/error counters.
# Admin-only, since request paths/status codes are operational data, not
# something every logged-in user needs.
# ---------------------------------------------------------------------------
@api_bp.route("/metrics", methods=["GET"])
@login_required
@role_required("admin")
def api_metrics():
    from app.metrics import get_metrics

    return api_success(get_metrics())
