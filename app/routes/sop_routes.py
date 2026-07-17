from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from app.services import sop_service
from app.decorators import permission_required
from app.validation import validate_sop_input
from app.logging_config import log_crud

sop_bp = Blueprint("sop", __name__, url_prefix="/sop")


@sop_bp.route("")
@login_required
def sop_list():
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config.get("ITEMS_PER_PAGE", 10)
    pagination = sop_service.list_sop(page=page, per_page=per_page)
    return render_template("sop_list.html", sops=pagination.items, pagination=pagination)


@sop_bp.route("/<int:sop_id>")
@login_required
def sop_view(sop_id):
    sop = sop_service.get_sop(sop_id)
    if sop is None:
        flash("SOP not found.")
        return redirect(url_for("sop.sop_list"))
    return render_template("sop_view.html", sop=sop)


@sop_bp.route("/new", methods=["GET", "POST"])
@login_required
@permission_required("create_sop")
def sop_new():
    if request.method == "POST":
        errors = validate_sop_input(request.form)
        if errors:
            for message in errors:
                flash(message)
            return render_template("sop_form.html", sop=request.form, mode="new")
        sop = sop_service.create_sop(request.form, user_id=current_user.id)
        log_crud("CREATE", "SOP", sop.id, current_user.username)
        flash("SOP added successfully.")
        return redirect(url_for("sop.sop_list"))

    return render_template("sop_form.html", sop=None, mode="new")


@sop_bp.route("/<int:sop_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("edit_sop")
def sop_edit(sop_id):
    sop = sop_service.get_sop(sop_id)
    if sop is None:
        flash("SOP not found.")
        return redirect(url_for("sop.sop_list"))

    if request.method == "POST":
        errors = validate_sop_input(request.form)
        if errors:
            for message in errors:
                flash(message)
            return render_template(
                "sop_form.html", sop=request.form, mode="edit", sop_id=sop_id
            )
        sop_service.update_sop(sop, request.form)
        log_crud("UPDATE", "SOP", sop.id, current_user.username)
        flash("SOP updated successfully.")
        return redirect(url_for("sop.sop_view", sop_id=sop_id))

    return render_template("sop_form.html", sop=sop, mode="edit", sop_id=sop_id)


@sop_bp.route("/<int:sop_id>/delete", methods=["POST"])
@login_required
@permission_required("delete_sop")
def sop_delete(sop_id):
    sop = sop_service.get_sop(sop_id)
    if sop is None:
        flash("SOP not found.")
        return redirect(url_for("sop.sop_list"))
    sop_service.delete_sop(sop)
    log_crud("DELETE", "SOP", sop.id, current_user.username)
    flash("SOP deleted.")
    return redirect(url_for("sop.sop_list"))
