import uuid
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from routes import login_required
from services import billing_service, inventory_service, auth_service

sales_bp = Blueprint("sales", __name__)


@sales_bp.route("/billing")
@login_required
def billing_list():
    db_path = current_app.config["DB_PATH"]
    sales = billing_service.list_sales(limit=100, db_path=db_path)
    return render_template("billing_list.html", sales=sales)


@sales_bp.route("/billing/new", methods=["GET", "POST"])
@login_required
def new_bill():
    db_path = current_app.config["DB_PATH"]
    settings = auth_service.get_store_settings(db_path=db_path)

    if request.method == "POST":
        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        unit_prices = request.form.getlist("unit_price[]")

        items = []
        for pid, qty, price in zip(product_ids, quantities, unit_prices):
            if pid and qty:
                items.append({"product_id": int(pid), "quantity": qty, "unit_price": price})

        cust_raw = request.form.get("customer_id", "").strip()
        customer_id = int(cust_raw) if cust_raw else None

        try:
            created = billing_service.create_sale(
                items=items,
                customer_id=customer_id,
                walkin_name=request.form.get("walkin_name", ""),
                walkin_phone=request.form.get("walkin_phone", ""),
                discount=request.form.get("discount", "0"),
                tax_rate=request.form.get("tax_rate", settings["default_tax_rate"]),
                paid_amount=request.form.get("paid_amount", "0"),
                payment_method=request.form.get("payment_method", "Cash"),
                sale_date=request.form.get("sale_date", date.today().isoformat()),
                submission_token=request.form.get("submission_token"),
                db_path=db_path,
            )
            flash(f"Bill {created['sale']['invoice_no']} created successfully!", "success")
            return redirect(url_for("sales.bill_detail", sale_id=created["sale"]["id"]))
        except Exception as exc:
            flash(str(exc), "danger")

    products = inventory_service.list_products(active_only=True, db_path=db_path)
    customers = billing_service.list_customers_with_balances(db_path=db_path)
    return render_template(
        "billing_new.html",
        products=products,
        customers=customers,
        default_tax_rate=settings["default_tax_rate"],
        today=date.today().isoformat(),
        submission_token=str(uuid.uuid4()),
    )


@sales_bp.route("/billing/<int:sale_id>")
@login_required
def bill_detail(sale_id):
    db_path = current_app.config["DB_PATH"]
    detail = billing_service.get_sale_detail(sale_id, db_path=db_path)
    if not detail:
        flash("Bill not found.", "danger")
        return redirect(url_for("sales.billing_list"))
    return render_template("bill_detail.html", detail=detail, today=date.today().isoformat())


@sales_bp.route("/billing/<int:sale_id>/void", methods=["POST"])
@login_required
def void_bill(sale_id):
    db_path = current_app.config["DB_PATH"]
    try:
        detail = billing_service.void_sale(sale_id, db_path=db_path)
        flash(f"Bill {detail['sale']['invoice_no']} has been voided and stock restored.", "warning")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("sales.bill_detail", sale_id=sale_id))


@sales_bp.route("/customers", methods=["GET", "POST"])
@login_required
def customers():
    db_path = current_app.config["DB_PATH"]
    if request.method == "POST":
        try:
            cust = billing_service.create_customer(
                name=request.form.get("name", ""),
                phone=request.form.get("phone", ""),
                address=request.form.get("address", ""),
                pincode=request.form.get("pincode", ""),
                notes=request.form.get("notes", ""),
                db_path=db_path,
            )
            flash(f"Customer '{cust['name']}' added.", "success")
            return redirect(url_for("sales.customers"))
        except Exception as exc:
            flash(str(exc), "danger")

    customer_list = billing_service.list_customers_with_balances(db_path=db_path)
    return render_template("customers.html", customers=customer_list, today=date.today().isoformat())


@sales_bp.route("/customers/<int:customer_id>")
@login_required
def customer_ledger(customer_id):
    db_path = current_app.config["DB_PATH"]
    ledger = billing_service.get_customer_ledger(customer_id, db_path=db_path)
    if not ledger:
        flash("Customer not found.", "danger")
        return redirect(url_for("sales.customers"))
    return render_template("customer_ledger.html", ledger=ledger, today=date.today().isoformat())


@sales_bp.route("/customers/pay", methods=["POST"])
@login_required
def record_payment():
    db_path = current_app.config["DB_PATH"]
    sale_id_raw = request.form.get("sale_id", "").strip()
    customer_id_raw = request.form.get("customer_id", "").strip()
    sale_id = int(sale_id_raw) if sale_id_raw else None
    customer_id = int(customer_id_raw) if customer_id_raw else None

    try:
        res = billing_service.record_customer_payment(
            amount=request.form.get("amount", "0"),
            payment_method=request.form.get("payment_method", "Cash"),
            payment_date=request.form.get("payment_date", date.today().isoformat()),
            customer_id=customer_id,
            sale_id=sale_id,
            note=request.form.get("note", ""),
            db_path=db_path,
        )
        flash(f"Recorded payment of ₹{res['allocated']} across {res['bills_updated']} bill(s).", "success")
    except Exception as exc:
        flash(str(exc), "danger")

    if sale_id:
        return redirect(url_for("sales.bill_detail", sale_id=sale_id))
    if customer_id:
        return redirect(url_for("sales.customer_ledger", customer_id=customer_id))
    return redirect(url_for("sales.customers"))