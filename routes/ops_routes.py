from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from routes import login_required
from services import return_service, quotation_service, report_service, billing_service, inventory_service, auth_service

ops_bp = Blueprint("ops", __name__)


@ops_bp.route("/returns", methods=["GET", "POST"])
@login_required
def returns():
    db_path = current_app.config["DB_PATH"]
    if request.method == "POST":
        sale_id = int(request.form.get("sale_id", 0))
        try:
            res = return_service.record_return(
                sale_id=sale_id,
                sale_item_id=int(request.form.get("sale_item_id", 0)),
                quantity=request.form.get("quantity", "0"),
                is_resalable=request.form.get("is_resalable") == "1",
                return_date=request.form.get("return_date", date.today().isoformat()),
                db_path=db_path,
            )
            flash(
                f"Return {res['return_no']} processed (₹{res['refund_amount']} — {res['settlement_type']}).",
                "success",
            )
            return redirect(url_for("ops.returns", sale_id=sale_id))
        except Exception as exc:
            flash(str(exc), "danger")
            return redirect(url_for("ops.returns", sale_id=sale_id))

    selected_sale_id = request.args.get("sale_id", type=int)
    selected_sale = billing_service.get_sale_detail(selected_sale_id, db_path=db_path) if selected_sale_id else None
    completed_sales = [s for s in billing_service.list_sales(limit=100, db_path=db_path) if s["status"] == "COMPLETED"]
    return_history = return_service.list_returns(db_path=db_path)

    return render_template(
        "returns.html",
        completed_sales=completed_sales,
        selected_sale=selected_sale,
        returns=return_history,
        today=date.today().isoformat(),
    )


@ops_bp.route("/quotations", methods=["GET", "POST"])
@login_required
def quotations():
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

        try:
            created = quotation_service.create_quotation(
                customer_name=request.form.get("customer_name", ""),
                items=items,
                customer_phone=request.form.get("customer_phone", ""),
                discount=request.form.get("discount", "0"),
                tax_rate=request.form.get("tax_rate", settings["default_tax_rate"]),
                quote_date=request.form.get("quote_date", date.today().isoformat()),
                db_path=db_path,
            )
            flash(f"Quotation {created['quotation']['quote_no']} created.", "success")
            return redirect(url_for("ops.quotation_detail", quote_id=created["quotation"]["id"]))
        except Exception as exc:
            flash(str(exc), "danger")

    products = inventory_service.list_products(active_only=True, db_path=db_path)
    quote_list = quotation_service.list_quotations(db_path=db_path)
    return render_template(
        "quotations.html",
        products=products,
        quotations=quote_list,
        default_tax_rate=settings["default_tax_rate"],
        today=date.today().isoformat(),
    )


@ops_bp.route("/quotations/<int:quote_id>")
@login_required
def quotation_detail(quote_id):
    db_path = current_app.config["DB_PATH"]
    detail = quotation_service.get_quotation_detail(quote_id, db_path=db_path)
    if not detail:
        flash("Quotation not found.", "danger")
        return redirect(url_for("ops.quotations"))
    customers = billing_service.list_customers_with_balances(db_path=db_path)
    return render_template("quotation_detail.html", detail=detail, customers=customers)


@ops_bp.route("/quotations/<int:quote_id>/status", methods=["POST"])
@login_required
def quotation_status(quote_id):
    db_path = current_app.config["DB_PATH"]
    try:
        quotation_service.update_quotation_status(
            quote_id=quote_id,
            status=request.form.get("status", ""),
            db_path=db_path,
        )
        flash("Quotation status updated.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("ops.quotation_detail", quote_id=quote_id))


@ops_bp.route("/quotations/<int:quote_id>/convert", methods=["POST"])
@login_required
def quotation_convert(quote_id):
    db_path = current_app.config["DB_PATH"]
    cust_raw = request.form.get("customer_id", "").strip()
    customer_id = int(cust_raw) if cust_raw else None
    try:
        sale = quotation_service.convert_quotation_to_sale(
            quote_id=quote_id,
            paid_amount=request.form.get("paid_amount", "0"),
            payment_method=request.form.get("payment_method", "Cash"),
            customer_id=customer_id,
            db_path=db_path,
        )
        flash(f"Converted quotation into Bill {sale['sale']['invoice_no']}!", "success")
        return redirect(url_for("sales.bill_detail", sale_id=sale["sale"]["id"]))
    except Exception as exc:
        flash(str(exc), "danger")
        return redirect(url_for("ops.quotation_detail", quote_id=quote_id))


@ops_bp.route("/reports")
@login_required
def reports():
    db_path = current_app.config["DB_PATH"]
    selected_date = request.args.get("date", date.today().isoformat())
    selected_month = request.args.get("month", date.today().strftime("%Y-%m"))

    daily = report_service.daily_sales_report(selected_date, db_path=db_path)
    monthly = report_service.monthly_sales_report(selected_month, db_path=db_path)
    inv_val = report_service.inventory_valuation_report(db_path=db_path)
    low_stock = inventory_service.get_low_stock_products(db_path=db_path)
    dues = report_service.outstanding_reports(db_path=db_path)

    return render_template(
        "reports.html",
        selected_date=selected_date,
        selected_month=selected_month,
        daily=daily,
        monthly=monthly,
        inv_val=inv_val,
        low_stock=low_stock,
        dues=dues,
    )