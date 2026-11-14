import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, send_from_directory
from werkzeug.utils import secure_filename
from routes import login_required
from services import auth_service, report_service, inventory_service, backup_service, external_api

main_bp = Blueprint("main", __name__)


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = auth_service.authenticate_user(username, password, db_path=current_app.config["DB_PATH"])
        if user:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            backup_service.run_daily_auto_backup(
                db_path=current_app.config["DB_PATH"],
                backup_dir=current_app.config["BACKUP_DIR"],
            )
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("main.dashboard"))
        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@main_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.login"))


@main_bp.route("/")
@login_required
def dashboard():
    db_path = current_app.config["DB_PATH"]
    summary = report_service.get_dashboard_summary(db_path=db_path)
    low_stock_items = inventory_service.get_low_stock_products(db_path=db_path)
    return render_template("dashboard.html", summary=summary, low_stock_items=low_stock_items)


@main_bp.route("/pin-lookup", methods=["GET", "POST"])
@login_required
def pin_lookup():
    result = None
    searched_pin = ""
    if request.method == "POST":
        searched_pin = request.form.get("pincode", "").strip()
        result = external_api.lookup_indian_pincode(searched_pin)
    return render_template("pin_lookup.html", result=result, searched_pin=searched_pin)


@main_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    db_path = current_app.config["DB_PATH"]
    backup_dir = current_app.config["BACKUP_DIR"]

    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "update_store":
                auth_service.update_store_settings(
                    store_name=request.form.get("store_name", ""),
                    store_address=request.form.get("store_address", ""),
                    store_phone=request.form.get("store_phone", ""),
                    default_tax_rate=request.form.get("default_tax_rate", "0"),
                    db_path=db_path,
                )
                flash("Store settings saved.", "success")
            elif action == "change_password":
                ok, msg = auth_service.change_password(
                    user_id=session["user_id"],
                    current_password=request.form.get("current_password", ""),
                    new_password=request.form.get("new_password", ""),
                    db_path=db_path,
                )
                flash(msg, "success" if ok else "danger")
        except Exception as exc:
            flash(str(exc), "danger")
        return redirect(url_for("main.settings"))

    backups = backup_service.list_backups(backup_dir=backup_dir)
    return render_template("settings.html", backups=backups)


@main_bp.route("/settings/backup/manual", methods=["POST"])
@login_required
def create_manual_backup():
    try:
        path = backup_service.create_backup(
            db_path=current_app.config["DB_PATH"],
            backup_dir=current_app.config["BACKUP_DIR"],
            prefix="manual",
        )
        flash(f"Manual backup created: {os.path.basename(path)}", "success")
    except Exception as exc:
        flash(f"Backup failed: {exc}", "danger")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/backup/download/<filename>")
@login_required
def download_backup(filename):
    safe_name = secure_filename(filename)
    if not safe_name.endswith(".db"):
        flash("Invalid backup file requested.", "danger")
        return redirect(url_for("main.settings"))
    backup_dir = os.path.abspath(current_app.config["BACKUP_DIR"])
    return send_from_directory(backup_dir, safe_name, as_attachment=True)