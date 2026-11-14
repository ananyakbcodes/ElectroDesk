import os
import sys

# Allow running directly via `python database/seed.py`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.db import init_db
from services import inventory_service, billing_service, purchase_service, quotation_service


def seed_demo_data():
    init_db()
    if inventory_service.list_products():
        print("Database already contains products. Skipping seed to protect existing data.")
        return

    sample_products = [
        ("Finolex 1.5 sq mm FR PVC Wire (Red)", "metre", "24.00", "17.50", "180.00", "50.00"),
        ("Finolex 2.5 sq mm FR PVC Wire (Black)", "metre", "38.00", "28.00", "90.00", "40.00"),
        ("Anchor Roma 6A 1-Way Switch", "pcs", "28.00", "18.00", "150.00", "30.00"),
        ("Anchor Roma 16A 3-Pin Socket", "pcs", "85.00", "58.00", "45.00", "15.00"),
        ("Havells 16A SP C-Curve MCB", "pcs", "210.00", "152.00", "24.00", "10.00"),
        ("Legrand 32A DP Isolator MCB", "pcs", "460.00", "345.00", "6.00", "8.00"),
        ("Crompton 9W Cool Day LED Bulb", "pcs", "95.00", "62.00", "60.00", "15.00"),
        ("1-inch Heavy PVC Conduit Pipe (3m)", "pcs", "115.00", "82.00", "35.00", "10.00"),
        ("Steel Grip PVC Insulation Tape", "roll", "18.00", "11.00", "80.00", "20.00"),
    ]

    created = []
    for name, unit, sp, cp, stock, min_stk in sample_products:
        created.append(inventory_service.add_product(name, unit, sp, cp, stock, min_stk))

    sup = purchase_service.create_supplier(
        name="Goa Electrical Distributors Pvt Ltd",
        phone="0832-2421100",
        address="EDC Complex, Patto, Panaji",
        pincode="403001",
        notes="Authorized Havells & Finolex distributor",
    )
    purchase_service.record_purchase(
        supplier_id=sup["id"],
        items=[{"product_id": created[4]["id"], "quantity": "10", "unit_cost": "152.00"}],
        supplier_invoice_no="GED-2026-441",
        paid_amount="1000.00",
        payment_method="UPI",
    )

    contractor = billing_service.create_customer(
        name="Prakash Naik (Licensed Electrician)",
        phone="9822145678",
        address="Porvorim, Bardez",
        pincode="403521",
        notes="Monthly site account",
    )
    billing_service.create_sale(
        items=[
            {"product_id": created[0]["id"], "quantity": "45.5"},
            {"product_id": created[2]["id"], "quantity": "20"},
        ],
        customer_id=contractor["id"],
        paid_amount="1000.00",
        payment_method="UPI",
    )

    quotation_service.create_quotation(
        customer_name="Desai Villa Construction",
        customer_phone="9823098765",
        items=[
            {"product_id": created[1]["id"], "quantity": "90"},
            {"product_id": created[5]["id"], "quantity": "4"},
        ],
    )

    print("Sample electrical store data seeded successfully!")


if __name__ == "__main__":
    seed_demo_data()