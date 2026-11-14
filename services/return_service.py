from datetime import date
from decimal import Decimal
from database.db import get_connection, to_decimal


def _next_return_no(conn, r_date_str: str) -> str:
    year = r_date_str[:4]
    row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM returns").fetchone()
    return f"RET-{year}-{int(row['next_id']):04d}"


def record_return(
    sale_id: int,
    sale_item_id: int,
    quantity,
    is_resalable: bool = True,
    return_date: str | None = None,
    db_path: str | None = None,
) -> dict:
    """Process a product return against a completed sale (FR-22 to FR-25)."""
    ret_qty = to_decimal(quantity)
    if ret_qty <= Decimal("0.00"):
        raise ValueError("Return quantity must be greater than zero.")
    r_date = (return_date or date.today().isoformat()).strip()

    conn = get_connection(db_path)
    try:
        sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        if not sale or sale["status"] != "COMPLETED":
            raise ValueError("Only completed bills can accept returns.")

        item = conn.execute(
            "SELECT * FROM sale_items WHERE id = ? AND sale_id = ?",
            (sale_item_id, sale_id),
        ).fetchone()
        if not item:
            raise ValueError("Selected line item does not belong to this bill.")

        max_returnable = to_decimal(item["quantity"]) - to_decimal(item["returned_qty"])
        if ret_qty > max_returnable:
            raise ValueError(f"Cannot return {ret_qty}; maximum returnable quantity is {max_returnable}.")

        unit_price = to_decimal(item["unit_price"])
        tax_pct = to_decimal(sale["tax_rate"])
        raw_refund = to_decimal(ret_qty * unit_price * (Decimal("1") + tax_pct / Decimal("100")))
        current_net = to_decimal(sale["net_amount"])
        refund_amount = min(raw_refund, current_net)

        current_paid = to_decimal(sale["paid_amount"])
        unpaid_balance = current_net - current_paid
        credit_reduced = min(unpaid_balance, refund_amount)
        cash_refund = refund_amount - credit_reduced

        new_net = current_net - refund_amount
        new_paid = current_paid - cash_refund
        settlement_type = "CASH_REFUND" if cash_refund > Decimal("0.00") else "CREDIT_ADJUSTED"

        return_no = _next_return_no(conn, r_date)

        conn.execute(
            """
            INSERT INTO returns (
                return_no, sale_id, sale_item_id, product_id, quantity, unit_price,
                refund_amount, is_resalable, settlement_type, return_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                return_no,
                sale_id,
                sale_item_id,
                item["product_id"],
                ret_qty,
                unit_price,
                refund_amount,
                1 if is_resalable else 0,
                settlement_type,
                r_date,
            ),
        )

        conn.execute(
            "UPDATE sale_items SET returned_qty = ? WHERE id = ?",
            (to_decimal(item["returned_qty"]) + ret_qty, sale_item_id),
        )
        conn.execute(
            "UPDATE sales SET net_amount = ?, paid_amount = ? WHERE id = ?",
            (new_net, new_paid, sale_id),
        )

        if cash_refund > Decimal("0.00"):
            conn.execute(
                """
                INSERT INTO customer_payments (customer_id, sale_id, amount, payment_method, entry_type, payment_date, note)
                VALUES (?, ?, ?, 'Cash', 'REFUND', ?, ?)
                """,
                (sale["customer_id"], sale_id, cash_refund, r_date, f"Refund for {return_no} on {sale['invoice_no']}"),
            )

        if is_resalable:
            prod = conn.execute("SELECT stock_qty FROM products WHERE id = ?", (item["product_id"],)).fetchone()
            prev_qty = to_decimal(prod["stock_qty"])
            new_qty = prev_qty + ret_qty
            conn.execute("UPDATE products SET stock_qty = ? WHERE id = ?", (new_qty, item["product_id"]))
            conn.execute(
                """
                INSERT INTO stock_movements (product_id, movement_type, quantity_change, previous_qty, new_qty, reference_code, note)
                VALUES (?, 'RETURN', ?, ?, ?, ?, ?)
                """,
                (item["product_id"], ret_qty, prev_qty, new_qty, return_no, f"Resalable return on {sale['invoice_no']}"),
            )

        conn.commit()
        return {
            "return_no": return_no,
            "refund_amount": str(refund_amount),
            "settlement_type": settlement_type,
            "cash_refund": str(cash_refund),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_returns(db_path: str | None = None) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT r.*, s.invoice_no, p.name AS product_name, p.unit
            FROM returns r
            JOIN sales s ON s.id = r.sale_id
            JOIN products p ON p.id = r.product_id
            ORDER BY r.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()