from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from routes import login_required
from services import purchase_service, inventory_service

purchase_bp = Blueprint("purchases", __name__)


@purchase_bp.route("/suppliers", methods=["GET", "POST"])
@login_required
def suppliers():
    db_path = current_app.config["DB_PATH"]
    if request.method == "POST":
        try:
            sup = purchase_service.create_supplier(
                name=request.form.get("name", ""),
                phone=request.form.get("phone", ""),
                address=request.form.get("address", ""),
                pincode=request.form.get("pincode", ""),
                notes=request.form.get("notes", ""),
                db_path=db_path,
            )
            flash(f"Supplier '{sup['name']}' added.", "success")
            return redirect(url_for("purchases.suppliers"))
        except Exception as exc:
            flash(str(exc), "danger")

    supplier_list = purchase_service.list_suppliers_with_balances(db_path=db_path)
    return render_template("suppliers.html", suppliers=supplier_list)


@purchase_bp.route("/purchases", methods=["GET", "POST"])
@login_required
def purchases():
    db_path = current_app.config["DB_PATH"]
    if request.method == "POST":
        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        unit_costs = request.form.getlist("unit_cost[]")

        items = []
        for pid, qty, cost in zip(product_ids, quantities, unit_costs):
            if pid and qty:
                items.append({"product_id": int(pid), "quantity": qty, "unit_cost": cost})

        try:
            pur = purchase_service.record_purchase(
                supplier_id=int(request.form.get("supplier_id", 0)),
                items=items,
                supplier_invoice_no=request.form.get("supplier_invoice_no", ""),
                purchase_date=request.form.get("purchase_date", date.today().isoformat()),
                paid_amount=request.form.get("paid_amount", "0"),
                payment_method=request.form.get("payment_method", "Cash"),
                notes=request.form.get("notes", ""),
                db_path=db_path,
            )
            flash(f"Purchase {pur['purchase_no']} recorded and stock updated.", "success")
            return redirect(url_for("purchases.purchases"))
        except Exception as exc:
            flash(str(exc), "danger")

    suppliers_list = purchase_service.list_suppliers_with_balances(db_path=db_path)
    products = inventory_service.list_products(active_only=False, db_path=db_path)
    purchase_list = purchase_service.list_purchases(db_path=db_path)
    return render_template(
        "purchases.html",
        suppliers=suppliers_list,
        products=products,
        purchases=purchase_list,
        today=date.today().isoformat(),
    )


@purchase_bp.route("/purchases/<int:purchase_id>/pay", methods=["POST"])
@login_required
def pay_purchase(purchase_id):
    db_path = current_app.config["DB_PATH"]
    try:
        res = purchase_service.record_supplier_payment(
            purchase_id=purchase_id,
            amount=request.form.get("amount", "0"),
            payment_method=request.form.get("payment_method", "Cash"),
            payment_date=request.form.get("payment_date", date.today().isoformat()),
            note=request.form.get("note", ""),
            db_path=db_path,
        )
        flash(f"Payment recorded for {res['purchase_no']}. Remaining due: ₹{res['new_balance']}.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("purchases.purchases"))