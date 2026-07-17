from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from app.models.user import User
from app.logging_config import log_auth_event
from app.extensions import limiter

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            log_auth_event("LOGIN", username or "(blank)", success=False)
            flash("Invalid username or password.")
            return render_template("login.html")

        login_user(user)
        log_auth_event("LOGIN", user.username, success=True)
        flash("Logged in successfully.")
        next_page = request.args.get("next")
        return redirect(next_page or url_for("main.home"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    log_auth_event("LOGOUT", current_user.username, success=True)
    logout_user()
    flash("Logged out.")
    return redirect(url_for("auth.login"))
