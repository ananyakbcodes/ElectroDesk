from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from routes import login_required
from services import inventory_service

product_bp = Blueprint("products", __name__, url_prefix="/products")


@product_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    db_path = current_app.config["DB_PATH"]
    if request.method == "POST":
        try:
            prod = inventory_service.add_product(
                name=request.form.get("name", ""),
                unit=request.form.get("unit", "pcs"),
                selling_price=request.form.get("selling_price", "0"),
                purchase_cost=request.form.get("purchase_cost", "0"),
                initial_stock=request.form.get("initial_stock", "0"),
                min_stock_threshold=request.form.get("min_stock_threshold", "5"),
                db_path=db_path,
            )
            flash(f"Product '{prod['name']}' added with code {prod['product_code']}.", "success")
            return redirect(url_for("products.index"))
        except Exception as exc:
            flash(str(exc), "danger")

    search = request.args.get("search", "")
    products = inventory_service.list_products(search=search, active_only=False, db_path=db_path)
    return render_template(
        "products.html",
        products=products,
        search=search,
        allowed_units=inventory_service.ALLOWED_UNITS,
    )


@product_bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def edit(product_id):
    db_path = current_app.config["DB_PATH"]
    prod = inventory_service.get_product_by_id(product_id, db_path=db_path)
    if not prod:
        flash("Product not found.", "danger")
        return redirect(url_for("products.index"))

    if request.method == "POST":
        try:
            inventory_service.update_product(
                product_id=product_id,
                name=request.form.get("name", ""),
                unit=request.form.get("unit", "pcs"),
                selling_price=request.form.get("selling_price", "0"),
                purchase_cost=request.form.get("purchase_cost", "0"),
                min_stock_threshold=request.form.get("min_stock_threshold", "5"),
                is_active=request.form.get("is_active") == "1",
                db_path=db_path,
            )
            flash("Product updated successfully.", "success")
            return redirect(url_for("products.index"))
        except Exception as exc:
            flash(str(exc), "danger")

    return render_template(
        "product_edit.html",
        product=prod,
        allowed_units=inventory_service.ALLOWED_UNITS,
    )


@product_bp.route("/reconcile", methods=["GET", "POST"])
@login_required
def reconcile():
    db_path = current_app.config["DB_PATH"]
    if request.method == "POST":
        try:
            res = inventory_service.reconcile_stock(
                product_id=int(request.form.get("product_id")),
                counted_qty=request.form.get("counted_qty", "0"),
                note=request.form.get("note", ""),
                db_path=db_path,
            )
            flash(
                f"Reconciled {res['name']} ({res['product_code']}): "
                f"{res['previous_qty']} -> {res['counted_qty']} (Variance: {res['difference']}).",
                "success",
            )
            return redirect(url_for("products.reconcile"))
        except Exception as exc:
            flash(str(exc), "danger")

    products = inventory_service.list_products(active_only=True, db_path=db_path)
    movements = inventory_service.get_recent_stock_movements(limit=25, db_path=db_path)
    return render_template("reconcile.html", products=products, movements=movements)


@product_bp.route("/import", methods=["POST"])
@login_required
def import_csv():
    db_path = current_app.config["DB_PATH"]
    uploaded = request.files.get("csv_file")
    if not uploaded or not uploaded.filename:
        flash("Please choose a CSV file to upload.", "danger")
        return redirect(url_for("products.index"))

    try:
        content = uploaded.read().decode("utf-8-sig")
        result = inventory_service.import_products_csv(content, db_path=db_path)
        if result["imported"] > 0:
            flash(f"Imported {result['imported']} product(s) successfully.", "success")
        for err in result["errors"]:
            flash(err, "warning")
    except Exception as exc:
        flash(f"CSV import failed: {exc}", "danger")

    return redirect(url_for("products.index"))