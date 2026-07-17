from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from app.services import kb_service
from app.decorators import kb_editor_required, check_kb_ownership, permission_required
from app.validation import validate_kb_input
from app.logging_config import log_crud

kb_bp = Blueprint("kb", __name__, url_prefix="/kb")


@kb_bp.route("")
@login_required
def kb_list():
    category = request.args.get("category", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config.get("ITEMS_PER_PAGE", 10)
    pagination = kb_service.list_kb(category or None, page=page, per_page=per_page)
    return render_template(
        "kb_list.html",
        articles=pagination.items,
        pagination=pagination,
        selected_category=category,
    )


@kb_bp.route("/<int:article_id>")
@login_required
def kb_view(article_id):
    article = kb_service.get_kb(article_id)
    if article is None:
        flash("Article not found.")
        return redirect(url_for("kb.kb_list"))
    return render_template("kb_view.html", article=article)


@kb_bp.route("/new", methods=["GET", "POST"])
@login_required
@kb_editor_required
def kb_new():
    if request.method == "POST":
        errors = validate_kb_input(request.form)
        if errors:
            for message in errors:
                flash(message)
            return render_template("kb_form.html", article=request.form, mode="new")
        article = kb_service.create_kb(request.form, user_id=current_user.id)
        log_crud("CREATE", "KnowledgeBase", article.id, current_user.username)
        flash("Article added successfully.")
        return redirect(url_for("kb.kb_list"))

    return render_template("kb_form.html", article=None, mode="new")


@kb_bp.route("/<int:article_id>/edit", methods=["GET", "POST"])
@login_required
@kb_editor_required
def kb_edit(article_id):
    article = kb_service.get_kb(article_id)
    if article is None:
        flash("Article not found.")
        return redirect(url_for("kb.kb_list"))

    # IDOR fix: role check (kb_editor_required) alone doesn't prove this
    # article is theirs to edit — verify object-level ownership too.
    denied = check_kb_ownership(article)
    if denied is not None:
        return denied

    if request.method == "POST":
        errors = validate_kb_input(request.form)
        if errors:
            for message in errors:
                flash(message)
            return render_template(
                "kb_form.html", article=request.form, mode="edit", article_id=article_id
            )
        kb_service.update_kb(article, request.form)
        log_crud("UPDATE", "KnowledgeBase", article.id, current_user.username)
        flash("Article updated successfully.")
        return redirect(url_for("kb.kb_view", article_id=article_id))

    return render_template("kb_form.html", article=article, mode="edit", article_id=article_id)


@kb_bp.route("/<int:article_id>/delete", methods=["POST"])
@login_required
@permission_required("delete_kb")
def kb_delete(article_id):
    article = kb_service.get_kb(article_id)
    if article is None:
        flash("Article not found.")
        return redirect(url_for("kb.kb_list"))
    kb_service.delete_kb(article)
    log_crud("DELETE", "KnowledgeBase", article.id, current_user.username)
    flash("Article deleted.")
    return redirect(url_for("kb.kb_list"))
