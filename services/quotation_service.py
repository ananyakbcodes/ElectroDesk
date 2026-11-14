import uuid
from datetime import date
from decimal import Decimal
from database.db import get_connection, to_decimal
from services.billing_service import create_sale


def _next_quote_no(conn, q_date_str: str) -> str:
    year = q_date_str[:4]
    row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM quotations").fetchone()
    return f"QTN-{year}-{int(row['next_id']):04d}"


def create_quotation(
    customer_name: str,
    items: list[dict],
    customer_phone: str = "",
    discount=0,
    tax_rate=0,
    quote_date: str | None = None,
    db_path: str | None = None,
) -> dict:
    """Create a quotation without deducting inventory (FR-26)."""
    clean_cust = (customer_name or "").strip()
    if not clean_cust:
        raise ValueError("Customer or contractor name is required for a quotation.")
    if not items:
        raise ValueError("Add at least one item to the quotation.")

    q_date = (quote_date or date.today().isoformat()).strip()
    disc = to_decimal(discount)
    tax_pct = to_decimal(tax_rate)

    conn = get_connection(db_path)
    try:
        subtotal = Decimal("0.00")
        lines = []
        for entry in items:
            pid = int(entry["product_id"])
            qty = to_decimal(entry["quantity"])
            if qty <= Decimal("0.00"):
                raise ValueError("Quantity must be greater than zero.")
            prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
            if not prod:
                raise ValueError(f"Product ID {pid} not found.")
            price = to_decimal(entry.get("unit_price") or prod["selling_price"])
            line_total = to_decimal(qty * price)
            subtotal += line_total
            lines.append({"product_id": pid, "qty": qty, "price": price, "line_total": line_total})

        if disc > subtotal:
            raise ValueError("Discount cannot exceed quotation subtotal.")

        taxable = subtotal - disc
        tax_amount = to_decimal(taxable * (tax_pct / Decimal("100")))
        total_amount = taxable + tax_amount
        quote_no = _next_quote_no(conn, q_date)

        cur = conn.execute(
            """
            INSERT INTO quotations (quote_no, customer_name, customer_phone, subtotal, discount, tax_rate, tax_amount, total_amount, status, quote_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
            """,
            (quote_no, clean_cust, customer_phone.strip(), subtotal, disc, tax_pct, tax_amount, total_amount, q_date),
        )
        quote_id = cur.lastrowid

        for line in lines:
            conn.execute(
                """
                INSERT INTO quotation_items (quotation_id, product_id, quantity, unit_price, line_total)
                VALUES (?, ?, ?, ?, ?)
                """,
                (quote_id, line["product_id"], line["qty"], line["price"], line["line_total"]),
            )

        conn.commit()
        return get_quotation_detail(quote_id, db_path)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_quotation_status(quote_id: int, status: str, db_path: str | None = None) -> None:
    if status not in ("Pending", "Accepted", "Rejected"):
        raise ValueError("Invalid quotation status.")
    conn = get_connection(db_path)
    try:
        q = conn.execute("SELECT status FROM quotations WHERE id = ?", (quote_id,)).fetchone()
        if not q:
            raise ValueError("Quotation not found.")
        if q["status"] == "Converted":
            raise ValueError("Converted quotations cannot have their status changed.")
        conn.execute("UPDATE quotations SET status = ? WHERE id = ?", (status, quote_id))
        conn.commit()
    finally:
        conn.close()


def convert_quotation_to_sale(
    quote_id: int,
    paid_amount=0,
    payment_method: str = "Cash",
    customer_id: int | None = None,
    db_path: str | None = None,
) -> dict:
    """Convert an un-converted quotation into a completed sale once (FR-28)."""
    detail = get_quotation_detail(quote_id, db_path)
    if not detail:
        raise ValueError("Quotation not found.")
    q = detail["quotation"]
    if q["status"] == "Converted" or q["converted_sale_id"]:
        raise ValueError("This quotation has already been converted to a sale.")
    if q["status"] == "Rejected":
        raise ValueError("Rejected quotations cannot be converted to a sale.")

    sale_items = [
        {"product_id": item["product_id"], "quantity": item["quantity"], "unit_price": item["unit_price"]}
        for item in detail["items"]
    ]
    created = create_sale(
        items=sale_items,
        customer_id=customer_id,
        walkin_name=q["customer_name"],
        walkin_phone=q["customer_phone"] or "",
        discount=q["discount"],
        tax_rate=q["tax_rate"],
        paid_amount=paid_amount,
        payment_method=payment_method,
        submission_token=f"quote-{quote_id}-{uuid.uuid4().hex[:8]}",
        db_path=db_path,
    )

    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE quotations SET status = 'Converted', converted_sale_id = ? WHERE id = ?",
            (created["sale"]["id"], quote_id),
        )
        conn.commit()
    finally:
        conn.close()

    return created


def get_quotation_detail(quote_id: int, db_path: str | None = None) -> dict | None:
    conn = get_connection(db_path)
    try:
        q = conn.execute("SELECT * FROM quotations WHERE id = ?", (quote_id,)).fetchone()
        if not q:
            return None
        items = conn.execute(
            """
            SELECT qi.*, p.name AS product_name, p.product_code, p.unit
            FROM quotation_items qi
            JOIN products p ON p.id = qi.product_id
            WHERE qi.quotation_id = ?
            """,
            (quote_id,),
        ).fetchall()
        return {"quotation": dict(q), "items": [dict(i) for i in items]}
    finally:
        conn.close()


def list_quotations(db_path: str | None = None) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM quotations ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()