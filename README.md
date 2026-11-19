# ElectroDesk — Electrical Retail Management & Inventory Intelligence System

An offline-first retail billing, inventory, and contractor credit (*khata*) management system built for electrical supply stores using the **Waterfall SDLC** methodology.

## 1. Problem Statement
Traditional electrical retail counters rely on physical books and registers to track daily sales, stock balances, supplier purchases, and contractor credit dues. Manual record-keeping is slow, prone to calculation errors (especially on mixed units like discrete switches in `pcs` alongside cut-to-length wires in decimal `metre`), offers no low-stock alerts, and leaves business records without backups. **ElectroDesk** digitalizes all store books into a single, audit-safe application.

## 2. Core Features (SRS v1.2 — 46 Functional Requirements)
* **Mixed-Unit Inventory & Catalog:** Auto-SKU generation (`ELC-XXXX`), `pcs` and decimal `metre` tracking, Day-1 Opening Stock, bulk CSV upload with row-level error reporting, physical shelf reconciliation, and dashboard low-stock alerts.
* **Atomic Counter Billing & Print Receipts:** Sequential invoices (`INV-YYYY-XXXX`), exact `Decimal` (`ROUND_HALF_UP`) math, historical price snapshots, clean `@media print` receipts, and audit-safe **Void Bill** (`VOIDED`) reversals.
* **Customer Credit (*Khata*) Ledgers:** Contractor accounts with chronological (FIFO) lump-sum cash/UPI payment allocation across unpaid bills.
* **Supplier Purchases & Payables:** Inward stock replenishment from vendor bills and outward supplier payment tracking.
* **Returns & Quotations:** Condition-based sales returns (`RESALABLE` vs. `DAMAGED`) and house-wiring estimates (`QTN-YYYY-XXXX`) with a one-time conversion lock.
* **Backups, Security & External API:** Daily `.db` snapshots with `PRAGMA integrity_check` verification, salted password login, `X-API-Key` REST endpoints, and India Post PIN code lookup.

## 3. Technology Stack
* **Frontend:** HTML5, Jinja2 Templates, CSS3 (`@media print`), Vanilla JavaScript
* **Backend:** Python 3.14 / 3.11, Flask 3.x (Modular Blueprints), Python `decimal` (`ROUND_HALF_UP`)
* **Database:** SQLite 3 (WAL Mode, `PRAGMA foreign_keys = ON`, 15 normalized tables)
* **Testing & CI/CD:** Pytest 9.2.0 (`tmp_path` fixtures, `unittest.mock`), GitHub Actions (`ubuntu-latest`)

## 4. Database Architecture (15 Normalized Tables)
```mermaid
erDiagram
    PRODUCTS ||--o{ STOCK_MOVEMENTS : "logs audit trail"
    PRODUCTS ||--o{ SALE_ITEMS : "billed in"
    PRODUCTS ||--o{ PURCHASE_ITEMS : "restocked via"
    PRODUCTS ||--o{ QUOTATION_ITEMS : "estimated in"
    PRODUCTS ||--o{ SALES_RETURNS : "returned in"
    CUSTOMERS ||--o{ SALES : "places"
    CUSTOMERS ||--o{ CUSTOMER_PAYMENTS : "settles credit"
    CUSTOMERS ||--o{ QUOTATIONS : "requests"
    SALES ||--|{ SALE_ITEMS : "contains"
    SALES ||--o{ SALES_RETURNS : "references"
    QUOTATIONS ||--|{ QUOTATION_ITEMS : "lists"
    SUPPLIERS ||--o{ PURCHASES : "supplies"
    SUPPLIERS ||--o{ SUPPLIER_PAYMENTS : "receives"
    PURCHASES ||--|{ PURCHASE_ITEMS : "contains"
