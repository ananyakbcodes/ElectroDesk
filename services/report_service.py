from datetime import date
from decimal import Decimal
from database.db import get_connection, to_decimal


def get_dashboard_summary(db_path: str | None = None) -> dict:
    today = date.today().isoformat()
    conn = get_connection(db_path)
    try:
        sales_today = conn.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(SUM(CAST(net_amount AS REAL)), 0) AS total
            FROM sales WHERE status = 'COMPLETED' AND sale_date = ?
            """,
            (today,),
        ).fetchone()
        low_stock = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM products
            WHERE is_active = 1 AND CAST(stock_qty AS REAL) <= CAST(min_stock_threshold AS REAL)
            """
        ).fetchone()
        cust_due = conn.execute(
            """
            SELECT COALESCE(SUM(CAST(net_amount AS REAL) - CAST(paid_amount AS REAL)), 0) AS due
            FROM sales WHERE status = 'COMPLETED'
            """
        ).fetchone()
        sup_due = conn.execute(
            "SELECT COALESCE(SUM(CAST(total_amount AS REAL) - CAST(paid_amount AS REAL)), 0) AS due FROM purchases"
        ).fetchone()

        return {
            "today": today,
            "today_bills_count": int(sales_today["cnt"]),
            "today_sales_total": str(to_decimal(sales_today["total"])),
            "low_stock_count": int(low_stock["cnt"]),
            "customer_receivable": str(to_decimal(cust_due["due"])),
            "supplier_payable": str(to_decimal(sup_due["due"])),
        }
    finally:
        conn.close()


def daily_sales_report(selected_date: str, db_path: str | None = None) -> dict:
    """FR-29: Daily Sales Report."""
    conn = get_connection(db_path)
    try:
        bills = conn.execute(
            """
            SELECT s.*, c.name AS customer_name
            FROM sales s LEFT JOIN customers c ON c.id = s.customer_id
            WHERE s.status = 'COMPLETED' AND s.sale_date = ?
            ORDER BY s.id ASC
            """,
            (selected_date,),
        ).fetchall()

        total_sales = Decimal("0.00")
        total_collected = Decimal("0.00")
        rows = []
        for b in bills:
            d = dict(b)
            net = to_decimal(d["net_amount"])
            paid = to_decimal(d["paid_amount"])
            d["balance"] = str(net - paid)
            total_sales += net
            total_collected += paid
            rows.append(d)

        return {
            "date": selected_date,
            "bills": rows,
            "total_sales": str(total_sales),
            "total_collected": str(total_collected),
            "total_credit": str(total_sales - total_collected),
        }
    finally:
        conn.close()


def monthly_sales_report(year_month: str, db_path: str | None = None) -> dict:
    """FR-30: Monthly Sales Report (year_month format: 'YYYY-MM')."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                sale_date,
                COUNT(*) AS bill_count,
                SUM(CAST(net_amount AS REAL)) AS day_total,
                SUM(CAST(paid_amount AS REAL)) AS day_paid
            FROM sales
            WHERE status = 'COMPLETED' AND sale_date LIKE ?
            GROUP BY sale_date
            ORDER BY sale_date ASC
            """,
            (f"{year_month}%",),
        ).fetchall()

        days = []
        month_total = Decimal("0.00")
        month_paid = Decimal("0.00")
        for r in rows:
            dt = to_decimal(r["day_total"])
            dp = to_decimal(r["day_paid"])
            month_total += dt
            month_paid += dp
            days.append({
                "sale_date": r["sale_date"],
                "bill_count": int(r["bill_count"]),
                "day_total": str(dt),
                "day_paid": str(dp),
            })

        return {
            "year_month": year_month,
            "days": days,
            "month_total": str(month_total),
            "month_paid": str(month_paid),
            "month_credit": str(month_total - month_paid),
        }
    finally:
        conn.close()


def inventory_valuation_report(db_path: str | None = None) -> dict:
    """FR-31: Active inventory quantities and stock valuation."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM products WHERE is_active = 1 ORDER BY name ASC").fetchall()
        items = []
        total_value = Decimal("0.00")
        for r in rows:
            d = dict(r)
            val = to_decimal(to_decimal(d["stock_qty"]) * to_decimal(d["purchase_cost"]))
            d["stock_value"] = str(val)
            total_value += val
            items.append(d)
        return {"items": items, "total_valuation": str(total_value)}
    finally:
        conn.close()


def outstanding_reports(db_path: str | None = None) -> dict:
    """FR-33 & FR-34: Customer and Supplier open balances."""
    conn = get_connection(db_path)
    try:
        cust_bills = conn.execute(
            """
            SELECT s.id, s.invoice_no, s.sale_date, s.net_amount, s.paid_amount, c.name AS customer_name, c.phone
            FROM sales s
            JOIN customers c ON c.id = s.customer_id
            WHERE s.status = 'COMPLETED' AND (CAST(s.net_amount AS REAL) - CAST(s.paid_amount AS REAL)) > 0.001
            ORDER BY s.sale_date ASC
            """
        ).fetchall()

        sup_bills = conn.execute(
            """
            SELECT p.id, p.purchase_no, p.supplier_invoice_no, p.purchase_date, p.total_amount, p.paid_amount, s.name AS supplier_name, s.phone
            FROM purchases p
            JOIN suppliers s ON s.id = p.supplier_id
            WHERE (CAST(p.total_amount AS REAL) - CAST(p.paid_amount AS REAL)) > 0.001
            ORDER BY p.purchase_date ASC
            """
        ).fetchall()

        c_list = []
        for r in cust_bills:
            d = dict(r)
            d["balance"] = str(to_decimal(d["net_amount"]) - to_decimal(d["paid_amount"]))
            c_list.append(d)

        s_list = []
        for r in sup_bills:
            d = dict(r)
            d["balance"] = str(to_decimal(d["total_amount"]) - to_decimal(d["paid_amount"]))
            s_list.append(d)

        return {"customer_dues": c_list, "supplier_dues": s_list}
    finally:
        conn.close()
        