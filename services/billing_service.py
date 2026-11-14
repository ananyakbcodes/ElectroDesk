import uuid
from datetime import date
from decimal import Decimal
from database.db import get_connection, to_decimal


def _next_invoice_no(conn, sale_date_str: str) -> str:
    year = sale_date_str[:4]
    row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM sales").fetchone()
    return f"INV-{year}-{int(row['next_id']):04d}"


def create_customer(
    name: str,
    phone: str = "",
    address: str = "",
    pincode: str = "",
    notes: str = "",
    db_path: str | None = None,
) -> dict:
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Customer name is required.")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO customers (name, phone, address, pincode, notes) VALUES (?, ?, ?, ?, ?)",
            (clean_name, phone.strip(), address.strip(), pincode.strip(), notes.strip()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_customers_with_balances(db_path: str | None = None) -> list[dict]:
    """Return all credit customers with total billed, paid, and outstanding balance (FR-14)."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                c.*,
                COALESCE(SUM(CASE WHEN s.status = 'COMPLETED' THEN CAST(s.net_amount AS REAL) ELSE 0 END), 0) AS total_billed,
                COALESCE(SUM(CASE WHEN s.status = 'COMPLETED' THEN CAST(s.paid_amount AS REAL) ELSE 0 END), 0) AS total_paid,
                COALESCE(SUM(CASE WHEN s.status = 'COMPLETED' THEN (CAST(s.net_amount AS REAL) - CAST(s.paid_amount AS REAL)) ELSE 0 END), 0) AS outstanding_balance
            FROM customers c
            LEFT JOIN sales s ON s.customer_id = c.id
            GROUP BY c.id
            ORDER BY outstanding_balance DESC, c.name ASC
            """
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["total_billed"] = str(to_decimal(d["total_billed"]))
            d["total_paid"] = str(to_decimal(d["total_paid"]))
            d["outstanding_balance"] = str(to_decimal(d["outstanding_balance"]))
            result.append(d)
        return result
    finally:
        conn.close()


def get_customer_ledger(customer_id: int, db_path: str | None = None) -> dict | None:
    """Get a single customer's profile, bills, payment history, and total due."""
    conn = get_connection(db_path)
    try:
        cust = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not cust:
            return None
        bills = conn.execute(
            "SELECT * FROM sales WHERE customer_id = ? ORDER BY id DESC",
            (customer_id,),
        ).fetchall()
        payments = conn.execute(
            """
            SELECT cp.*, s.invoice_no
            FROM customer_payments cp
            LEFT JOIN sales s ON s.id = cp.sale_id
            WHERE cp.customer_id = ?
            ORDER BY cp.id DESC
            """,
            (customer_id,),
        ).fetchall()

        bill_list = []
        total_due = Decimal("0.00")
        for b in bills:
            bd = dict(b)
            bal = to_decimal(bd["net_amount"]) - to_decimal(bd["paid_amount"]) if bd["status"] == "COMPLETED" else Decimal("0.00")
            bd["balance"] = str(bal)
            total_due += bal
            bill_list.append(bd)

        return {
            "customer": dict(cust),
            "bills": bill_list,
            "payments": [dict(p) for p in payments],
            "total_due": str(total_due),
        }
    finally:
        conn.close()


def create_sale(
    items: list[dict],
    customer_id: int | None = None,
    walkin_name: str = "",
    walkin_phone: str = "",
    discount=0,
    tax_rate=0,
    paid_amount=0,
    payment_method: str = "Cash",
    sale_date: str | None = None,
    submission_token: str | None = None,
    db_path: str | None = None,
) -> dict:
    """
    Create a completed sale and deduct stock atomically (FR-08 to FR-15).
    `items`: list of dicts [{"product_id": int, "quantity": number, "unit_price": optional}]
    """
    if not items:
        raise ValueError("Add at least one product to create a bill.")

    token = (submission_token or str(uuid.uuid4())).strip()
    bill_date = (sale_date or date.today().isoformat()).strip()
    disc = to_decimal(discount)
    tax_pct = to_decimal(tax_rate)
    paid = to_decimal(paid_amount)

    if disc < 0 or tax_pct < 0 or paid < 0:
        raise ValueError("Discount, tax rate, and paid amount cannot be negative.")

    conn = get_connection(db_path)
    try:
        # FR-11: Prevent duplicate sale submission
        existing = conn.execute("SELECT id FROM sales WHERE submission_token = ?", (token,)).fetchone()
        if existing:
            raise ValueError("Duplicate bill submission blocked. This bill was already saved.")

        # Merge duplicate product rows if operator selected same item twice
        merged_qty: dict[int, Decimal] = {}
        custom_prices: dict[int, Decimal] = {}
        for entry in items:
            pid = int(entry["product_id"])
            qty = to_decimal(entry["quantity"])
            if qty <= Decimal("0.00"):
                raise ValueError("Quantity must be greater than zero.")
            merged_qty[pid] = merged_qty.get(pid, Decimal("0.00")) + qty
            if entry.get("unit_price") is not None and str(entry.get("unit_price")).strip() != "":
                custom_prices[pid] = to_decimal(entry["unit_price"])

        prepared_lines = []
        subtotal = Decimal("0.00")

        # FR-09: Validate stock availability for every item before modifying anything
        for pid, qty in merged_qty.items():
            prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
            if not prod:
                raise ValueError(f"Product ID {pid} does not exist.")
            if int(prod["is_active"]) != 1:
                raise ValueError(f"Product '{prod['name']}' is inactive and cannot be billed.")

            avail = to_decimal(prod["stock_qty"])
            if qty > avail:
                raise ValueError(
                    f"Insufficient stock for '{prod['name']}' ({prod['product_code']}): "
                    f"requested {qty} {prod['unit']}, available {avail} {prod['unit']}."
                )

            unit_price = custom_prices.get(pid, to_decimal(prod["selling_price"]))
            line_total = to_decimal(qty * unit_price)
            subtotal += line_total
            prepared_lines.append({
                "product_id": pid,
                "product_code": prod["product_code"],
                "name": prod["name"],
                "unit": prod["unit"],
                "avail": avail,
                "qty": qty,
                "unit_price": unit_price,
                "line_total": line_total,
            })

        if disc > subtotal:
            raise ValueError("Discount cannot exceed bill subtotal.")

        taxable = subtotal - disc
        tax_amount = to_decimal(taxable * (tax_pct / Decimal("100")))
        total_amount = taxable + tax_amount

        if paid > total_amount:
            raise ValueError(f"Paid amount (₹{paid}) cannot exceed bill total (₹{total_amount}).")

        if paid < total_amount and not customer_id:
            raise ValueError("Select a registered credit customer when leaving an unpaid balance.")

        invoice_no = _next_invoice_no(conn, bill_date)

        # FR-10: Save sale, items, payment, and stock deductions in one atomic transaction
        cur = conn.execute(
            """
            INSERT INTO sales (
                invoice_no, customer_id, walkin_name, walkin_phone,
                subtotal, discount, tax_rate, tax_amount, total_amount, net_amount, paid_amount,
                status, submission_token, sale_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?)
            """,
            (
                invoice_no,
                customer_id if customer_id else None,
                walkin_name.strip(),
                walkin_phone.strip(),
                subtotal,
                disc,
                tax_pct,
                tax_amount,
                total_amount,
                total_amount,
                paid,
                token,
                bill_date,
            ),
        )
        sale_id = cur.lastrowid

        for line in prepared_lines:
            conn.execute(
                """
                INSERT INTO sale_items (
                    sale_id, product_id, product_name_snapshot, unit_snapshot, quantity, unit_price, line_total
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sale_id,
                    line["product_id"],
                    line["name"],
                    line["unit"],
                    line["qty"],
                    line["unit_price"],
                    line["line_total"],
                ),
            )
            new_qty = line["avail"] - line["qty"]
            conn.execute("UPDATE products SET stock_qty = ? WHERE id = ?", (new_qty, line["product_id"]))
            conn.execute(
                """
                INSERT INTO stock_movements (product_id, movement_type, quantity_change, previous_qty, new_qty, reference_code, note)
                VALUES (?, 'SALE', ?, ?, ?, ?, ?)
                """,
                (line["product_id"], -line["qty"], line["avail"], new_qty, invoice_no, f"Sold on {invoice_no}"),
            )

        if paid > Decimal("0.00"):
            conn.execute(
                """
                INSERT INTO customer_payments (customer_id, sale_id, amount, payment_method, entry_type, payment_date, note)
                VALUES (?, ?, ?, ?, 'PAYMENT', ?, ?)
                """,
                (customer_id if customer_id else None, sale_id, paid, payment_method, bill_date, f"Initial payment on {invoice_no}"),
            )

        conn.commit()
        return get_sale_detail(sale_id, db_path)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_sale_detail(sale_id: int, db_path: str | None = None) -> dict | None:
    conn = get_connection(db_path)
    try:
        sale = conn.execute(
            """
            SELECT s.*, c.name AS customer_name, c.phone AS customer_phone, c.address AS customer_address
            FROM sales s
            LEFT JOIN customers c ON c.id = s.customer_id
            WHERE s.id = ?
            """,
            (sale_id,),
        ).fetchone()
        if not sale:
            return None
        items = conn.execute("SELECT * FROM sale_items WHERE sale_id = ? ORDER BY id ASC", (sale_id,)).fetchall()
        payments = conn.execute("SELECT * FROM customer_payments WHERE sale_id = ? ORDER BY id ASC", (sale_id,)).fetchall()
        returns = conn.execute(
            """
            SELECT r.*, p.name AS product_name
            FROM returns r JOIN products p ON p.id = r.product_id
            WHERE r.sale_id = ? ORDER BY r.id ASC
            """,
            (sale_id,),
        ).fetchall()

        sd = dict(sale)
        sd["balance"] = str(
            to_decimal(sd["net_amount"]) - to_decimal(sd["paid_amount"])
            if sd["status"] == "COMPLETED"
            else Decimal("0.00")
        )
        return {
            "sale": sd,
            "items": [dict(i) for i in items],
            "payments": [dict(p) for p in payments],
            "returns": [dict(r) for r in returns],
        }
    finally:
        conn.close()


def list_sales(limit: int = 50, db_path: str | None = None) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT s.*, c.name AS customer_name
            FROM sales s
            LEFT JOIN customers c ON c.id = s.customer_id
            ORDER BY s.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["balance"] = str(
                to_decimal(d["net_amount"]) - to_decimal(d["paid_amount"])
                if d["status"] == "COMPLETED"
                else Decimal("0.00")
            )
            result.append(d)
        return result
    finally:
        conn.close()


def record_customer_payment(
    amount,
    payment_method: str,
    payment_date: str | None = None,
    customer_id: int | None = None,
    sale_id: int | None = None,
    note: str = "",
    db_path: str | None = None,
) -> dict:
    """
    Record payment against a single bill OR allocate lump-sum across a customer's oldest unpaid bills (FR-12).
    """
    pay_amt = to_decimal(amount)
    if pay_amt <= Decimal("0.00"):
        raise ValueError("Payment amount must be greater than zero.")
    p_date = (payment_date or date.today().isoformat()).strip()

    conn = get_connection(db_path)
    try:
        if sale_id:
            sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
            if not sale or sale["status"] != "COMPLETED":
                raise ValueError("Completed bill not found.")
            balance = to_decimal(sale["net_amount"]) - to_decimal(sale["paid_amount"])
            if pay_amt > balance:
                raise ValueError(f"Payment (₹{pay_amt}) exceeds bill balance (₹{balance}).")

            new_paid = to_decimal(sale["paid_amount"]) + pay_amt
            conn.execute("UPDATE sales SET paid_amount = ? WHERE id = ?", (new_paid, sale_id))
            conn.execute(
                """
                INSERT INTO customer_payments (customer_id, sale_id, amount, payment_method, entry_type, payment_date, note)
                VALUES (?, ?, ?, ?, 'PAYMENT', ?, ?)
                """,
                (sale["customer_id"], sale_id, pay_amt, payment_method, p_date, note.strip() or f"Payment for {sale['invoice_no']}"),
            )
            conn.commit()
            return {"allocated": str(pay_amt), "bills_updated": 1}

        if not customer_id:
            raise ValueError("Specify either a bill or a credit customer.")

        unpaid_bills = conn.execute(
            """
            SELECT * FROM sales
            WHERE customer_id = ? AND status = 'COMPLETED'
              AND (CAST(net_amount AS REAL) - CAST(paid_amount AS REAL)) > 0.001
            ORDER BY sale_date ASC, id ASC
            """,
            (customer_id,),
        ).fetchall()

        total_open = sum((to_decimal(b["net_amount"]) - to_decimal(b["paid_amount"])) for b in unpaid_bills)
        if pay_amt > total_open:
            raise ValueError(f"Lump-sum payment (₹{pay_amt}) exceeds customer's total due (₹{total_open}).")

        remaining = pay_amt
        updated = 0
        for b in unpaid_bills:
            if remaining <= Decimal("0.00"):
                break
            bal = to_decimal(b["net_amount"]) - to_decimal(b["paid_amount"])
            alloc = min(bal, remaining)
            conn.execute("UPDATE sales SET paid_amount = ? WHERE id = ?", (to_decimal(b["paid_amount"]) + alloc, b["id"]))
            conn.execute(
                """
                INSERT INTO customer_payments (customer_id, sale_id, amount, payment_method, entry_type, payment_date, note)
                VALUES (?, ?, ?, ?, 'PAYMENT', ?, ?)
                """,
                (customer_id, b["id"], alloc, payment_method, p_date, note.strip() or f"Lump-sum allocation to {b['invoice_no']}"),
            )
            remaining -= alloc
            updated += 1

        conn.commit()
        return {"allocated": str(pay_amt), "bills_updated": updated}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def void_sale(sale_id: int, db_path: str | None = None) -> dict:
    """Void an erroneous completed bill and restore remaining unreturned stock (FR-15A, FR-38)."""
    conn = get_connection(db_path)
    try:
        sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        if not sale:
            raise ValueError("Sale not found.")
        if sale["status"] == "VOIDED":
            raise ValueError("This bill is already voided.")

        items = conn.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)).fetchall()
        for item in items:
            unreturned = to_decimal(item["quantity"]) - to_decimal(item["returned_qty"])
            if unreturned > Decimal("0.00"):
                prod = conn.execute("SELECT stock_qty FROM products WHERE id = ?", (item["product_id"],)).fetchone()
                prev_qty = to_decimal(prod["stock_qty"])
                new_qty = prev_qty + unreturned
                conn.execute("UPDATE products SET stock_qty = ? WHERE id = ?", (new_qty, item["product_id"]))
                conn.execute(
                    """
                    INSERT INTO stock_movements (product_id, movement_type, quantity_change, previous_qty, new_qty, reference_code, note)
                    VALUES (?, 'VOID_SALE', ?, ?, ?, ?, ?)
                    """,
                    (item["product_id"], unreturned, prev_qty, new_qty, sale["invoice_no"], f"Voided {sale['invoice_no']}"),
                )

        conn.execute("UPDATE sales SET status = 'VOIDED' WHERE id = ?", (sale_id,))
        conn.commit()
        return get_sale_detail(sale_id, db_path)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()