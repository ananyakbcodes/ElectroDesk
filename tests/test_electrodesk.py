import time
from unittest.mock import patch, MagicMock
import pytest
from config import Config
from database.db import to_decimal
from services import (
    inventory_service,
    billing_service,
    purchase_service,
    return_service,
    quotation_service,
    backup_service,
    external_api,
)


# 1. Inventory & Opening Stock Tests (FR-01 to FR-07)
def test_product_creation_opening_stock_and_low_stock(temp_db):
    wire = inventory_service.add_product(
        name="Finolex 1.5 sq mm Red Wire",
        unit="metre",
        selling_price="24.50",
        purchase_cost="18.00",
        initial_stock="45.50",
        min_stock_threshold="50.00",
        db_path=temp_db,
    )
    assert wire["product_code"] == "ELC-0001"
    assert to_decimal(wire["stock_qty"]) == to_decimal("45.50")

    low = inventory_service.get_low_stock_products(db_path=temp_db)
    assert len(low) == 1
    assert low[0]["product_code"] == "ELC-0001"


def test_stock_reconciliation_and_csv_import(temp_db):
    p = inventory_service.add_product("Anchor 6A Switch", "pcs", "25", "16", "100", "20", db_path=temp_db)
    variance = inventory_service.reconcile_stock(p["id"], "97", "Broken pieces removed", db_path=temp_db)
    assert variance["difference"] == "-3.00"

    csv_data = (
        "name,unit,selling_price,purchase_cost,stock_qty,min_stock_threshold\n"
        "Havells 16A MCB,pcs,210,155,30,10\n"
        "Invalid Negative Price,pcs,-50,10,5,2\n"
    )
    res = inventory_service.import_products_csv(csv_data, db_path=temp_db)
    assert res["imported"] == 1
    assert len(res["errors"]) == 1


# 2. Billing, Atomic Rollback, Credit & Voiding Tests (FR-08 to FR-15A)
def test_sale_deducts_stock_and_preserves_historical_price(temp_db):
    mcb = inventory_service.add_product("Legrand 32A DP MCB", "pcs", "450.00", "340.00", "10", "3", db_path=temp_db)
    sale = billing_service.create_sale(
        items=[{"product_id": mcb["id"], "quantity": "2"}],
        walkin_name="Ramesh Naik",
        paid_amount="900.00",
        payment_method="UPI",
        db_path=temp_db,
    )
    assert sale["sale"]["invoice_no"].startswith("INV-")
    assert to_decimal(sale["sale"]["net_amount"]) == to_decimal("900.00")

    # Stock reduced from 10 to 8
    updated_mcb = inventory_service.get_product_by_id(mcb["id"], db_path=temp_db)
    assert to_decimal(updated_mcb["stock_qty"]) == to_decimal("8.00")

    # Editing selling price later must NOT change historical invoice (FR-15)
    inventory_service.update_product(mcb["id"], "Legrand 32A DP MCB", "pcs", "520.00", "380.00", "3", True, db_path=temp_db)
    past_sale = billing_service.get_sale_detail(sale["sale"]["id"], db_path=temp_db)
    assert to_decimal(past_sale["items"][0]["unit_price"]) == to_decimal("450.00")


def test_insufficient_stock_rejects_sale_atomically(temp_db):
    bulb = inventory_service.add_product("Crompton 9W LED", "pcs", "110", "75", "3", "5", db_path=temp_db)
    with pytest.raises(ValueError, match="Insufficient stock"):
        billing_service.create_sale(
            items=[{"product_id": bulb["id"], "quantity": "5"}],
            paid_amount="550",
            db_path=temp_db,
        )
    # Stock must remain untouched at 3
    assert to_decimal(inventory_service.get_product_by_id(bulb["id"], db_path=temp_db)["stock_qty"]) == to_decimal("3.00")


def test_customer_credit_lump_sum_payment_and_void(temp_db):
    cust = billing_service.create_customer("Suresh Electricals (Contractor)", "9822001122", db_path=temp_db)
    pipe = inventory_service.add_product("1-inch PVC Conduit Pipe", "pcs", "120", "85", "50", "10", db_path=temp_db)

    billing_service.create_sale(
        items=[{"product_id": pipe["id"], "quantity": "5"}],
        customer_id=cust["id"],
        paid_amount="200",
        sale_date="2026-11-10",
        db_path=temp_db,
    )
    b2 = billing_service.create_sale(
        items=[{"product_id": pipe["id"], "quantity": "5"}],
        customer_id=cust["id"],
        paid_amount="0",
        sale_date="2026-11-12",
        db_path=temp_db,
    )
    # Total billed = 1200, paid = 200, due = 1000. Pay 600 lump-sum -> settles b1 (400) + 200 on b2
    alloc = billing_service.record_customer_payment("600", "Cash", customer_id=cust["id"], db_path=temp_db)
    assert alloc["bills_updated"] == 2

    ledger = billing_service.get_customer_ledger(cust["id"], db_path=temp_db)
    assert ledger["total_due"] == "400.00"

    # Voiding b2 restores 5 pipes (from 40 back to 45)
    billing_service.void_sale(b2["sale"]["id"], db_path=temp_db)
    assert to_decimal(inventory_service.get_product_by_id(pipe["id"], db_path=temp_db)["stock_qty"]) == to_decimal("45.00")


# 3. Supplier Purchases & Invoice Payments (FR-16 to FR-21)
def test_supplier_purchase_adds_stock_and_payment_does_not(temp_db):
    sup = purchase_service.create_supplier("Mapusa Electrical Wholesale", "0832225000", db_path=temp_db)
    fan = inventory_service.add_product("Usha Ceiling Fan", "pcs", "1850", "1450", "2", "2", db_path=temp_db)

    pur = purchase_service.record_purchase(
        supplier_id=sup["id"],
        items=[{"product_id": fan["id"], "quantity": "5", "unit_cost": "1480"}],
        supplier_invoice_no="MEW-901",
        paid_amount="3000",
        db_path=temp_db,
    )
    assert to_decimal(inventory_service.get_product_by_id(fan["id"], db_path=temp_db)["stock_qty"]) == to_decimal("7.00")

    pay_res = purchase_service.record_supplier_payment(pur["id"], "4400", "UPI", db_path=temp_db)
    assert pay_res["new_balance"] == "0.00"
    # Payment alone must not alter stock
    assert to_decimal(inventory_service.get_product_by_id(fan["id"], db_path=temp_db)["stock_qty"]) == to_decimal("7.00")


# 4. Product Returns & Quotations (FR-22 to FR-28)
def test_resalable_return_and_quotation_conversion(temp_db):
    sw = inventory_service.add_product("GM Modular Socket", "pcs", "90", "60", "20", "5", db_path=temp_db)
    sale = billing_service.create_sale(
        items=[{"product_id": sw["id"], "quantity": "4"}],
        paid_amount="360",
        db_path=temp_db,
    )
    sale_item_id = sale["items"][0]["id"]

    # Return 1 resalable socket -> stock becomes 17, cash refund 90
    ret = return_service.record_return(sale["sale"]["id"], sale_item_id, "1", is_resalable=True, db_path=temp_db)
    assert ret["settlement_type"] == "CASH_REFUND"
    assert ret["refund_amount"] == "90.00"
    assert to_decimal(inventory_service.get_product_by_id(sw["id"], db_path=temp_db)["stock_qty"]) == to_decimal("17.00")

    # Quotation does not deduct stock until converted once
    quote = quotation_service.create_quotation(
        customer_name="Site Engineer",
        items=[{"product_id": sw["id"], "quantity": "2"}],
        db_path=temp_db,
    )
    assert to_decimal(inventory_service.get_product_by_id(sw["id"], db_path=temp_db)["stock_qty"]) == to_decimal("17.00")

    quotation_service.convert_quotation_to_sale(quote["quotation"]["id"], paid_amount="180", db_path=temp_db)
    assert to_decimal(inventory_service.get_product_by_id(sw["id"], db_path=temp_db)["stock_qty"]) == to_decimal("15.00")

    # Second conversion must be blocked (FR-28)
    with pytest.raises(ValueError, match="already been converted"):
        quotation_service.convert_quotation_to_sale(quote["quotation"]["id"], paid_amount="180", db_path=temp_db)


# 5. Backup & Restore Verification (FR-39 to FR-42)
def test_backup_creation_and_restore_verification(temp_db, temp_backup_dir, tmp_path):
    inventory_service.add_product("Havells 2.5 sq mm Wire", "roll", "1950", "1600", "12", "3", db_path=temp_db)
    backup_file = backup_service.create_backup(db_path=temp_db, backup_dir=temp_backup_dir, prefix="test")

    restored_db = str(tmp_path / "restored_copy.db")
    assert backup_service.restore_backup_to_target(backup_file, restored_db) is True

    restored_products = inventory_service.list_products(db_path=restored_db)
    assert len(restored_products) == 1
    assert restored_products[0]["name"] == "Havells 2.5 sq mm Wire"


# 6. Security, Internal REST API, Mocked External API & Performance (FR-35, FR-43 to FR-45, Sec 5.2)
def test_unauthenticated_api_blocked(client):
    unauth = client.get("/api/products")
    assert unauth.status_code == 401


def test_authenticated_api_and_performance(client, auth_client):
    # Authenticated via API Key header works and meets < 2s performance target
    start = time.perf_counter()
    api_resp = client.get("/api/summary", headers={"X-API-Key": Config.INTERNAL_API_KEY})
    elapsed = time.perf_counter() - start
    assert api_resp.status_code == 200
    assert "today_sales_total" in api_resp.get_json()
    assert elapsed < 2.0

    # Dashboard page loads within < 3s target
    t0 = time.perf_counter()
    dash = auth_client.get("/")
    assert dash.status_code == 200
    assert (time.perf_counter() - t0) < 3.0


@patch("services.external_api.requests.get")
def test_external_pincode_api_mocked(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = [
        {
            "Status": "Success",
            "PostOffice": [
                {"Name": "Panaji H.O", "BranchType": "Head Post Office", "District": "North Goa", "State": "Goa"}
            ],
        }
    ]
    mock_get.return_value = mock_resp

    res = external_api.lookup_indian_pincode("403001")
    assert res["ok"] is True
    assert res["offices"][0]["district"] == "North Goa"

    bad = external_api.lookup_indian_pincode("12")
    assert bad["ok"] is False