from flask import Blueprint, render_template, request
from flask_login import login_required

from app.models.kb import KnowledgeBase
from app.models.sop import SOP
from app.services.kb_service import search_kb
from app.services.sop_service import search_sop

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def home():
    # AUDIT FIX (soft delete consistency): these previously counted every
    # row including soft-deleted ones (KnowledgeBase.query.count() has no
    # is_deleted filter), so the dashboard showed inflated counts that
    # included "deleted" articles/SOPs still lingering in the totals.
    count_kb = KnowledgeBase.query.filter_by(is_deleted=False).count()
    count_sop = SOP.query.filter_by(is_deleted=False).count()
    return render_template("home.html", count_kb=count_kb, count_sop=count_sop)


@main_bp.route("/search")
@login_required
def search():
    query = request.args.get("q", "").strip()
    kb_results = search_kb(query) if query else []
    sop_results = search_sop(query) if query else []
    return render_template(
        "search.html", query=query, kb_results=kb_results, sop_results=sop_results
    )
