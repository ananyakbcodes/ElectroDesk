PRAGMA foreign_keys = ON;

-- 1. Operator Authentication (FR-35 to FR-37)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 2. Store Configuration (FR-38A)
CREATE TABLE IF NOT EXISTS store_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    store_name TEXT NOT NULL DEFAULT 'ElectroDesk Electricals',
    store_address TEXT NOT NULL DEFAULT 'Main Market Road, Goa',
    store_phone TEXT NOT NULL DEFAULT '',
    default_tax_rate NUMERIC NOT NULL DEFAULT 0.00
);

-- 3. Product Catalog & Live Stock (FR-01 to FR-05)
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'pcs',
    selling_price NUMERIC NOT NULL CHECK (selling_price >= 0),
    purchase_cost NUMERIC NOT NULL DEFAULT 0.00 CHECK (purchase_cost >= 0),
    stock_qty NUMERIC NOT NULL DEFAULT 0.00 CHECK (stock_qty >= 0),
    min_stock_threshold NUMERIC NOT NULL DEFAULT 5.00 CHECK (min_stock_threshold >= 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 4. Stock Audit & Reconciliation Log (FR-04, FR-06, FR-38)
CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    movement_type TEXT NOT NULL CHECK (
        movement_type IN ('OPENING', 'PURCHASE', 'SALE', 'VOID_SALE', 'RETURN', 'RECONCILIATION')
    ),
    quantity_change NUMERIC NOT NULL,
    previous_qty NUMERIC NOT NULL,
    new_qty NUMERIC NOT NULL,
    reference_code TEXT,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- 5. Credit Customers & Contractors (FR-14)
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    pincode TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 6. Sales Bills / Invoices (FR-08 to FR-15A)
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no TEXT NOT NULL UNIQUE,
    customer_id INTEGER,
    walkin_name TEXT,
    walkin_phone TEXT,
    subtotal NUMERIC NOT NULL DEFAULT 0.00,
    discount NUMERIC NOT NULL DEFAULT 0.00,
    tax_rate NUMERIC NOT NULL DEFAULT 0.00,
    tax_amount NUMERIC NOT NULL DEFAULT 0.00,
    total_amount NUMERIC NOT NULL DEFAULT 0.00,
    net_amount NUMERIC NOT NULL DEFAULT 0.00,
    paid_amount NUMERIC NOT NULL DEFAULT 0.00,
    status TEXT NOT NULL DEFAULT 'COMPLETED' CHECK (status IN ('COMPLETED', 'VOIDED')),
    submission_token TEXT NOT NULL UNIQUE,
    sale_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- 7. Sales Line Items with Historical Price Snapshot (FR-08, FR-15)
CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    product_name_snapshot TEXT NOT NULL,
    unit_snapshot TEXT NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC NOT NULL CHECK (unit_price >= 0),
    line_total NUMERIC NOT NULL CHECK (line_total >= 0),
    returned_qty NUMERIC NOT NULL DEFAULT 0.00 CHECK (returned_qty >= 0),
    FOREIGN KEY (sale_id) REFERENCES sales(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- 8. Customer Payments & Return Refunds (FR-12, FR-13, FR-25)
CREATE TABLE IF NOT EXISTS customer_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    sale_id INTEGER,
    amount NUMERIC NOT NULL CHECK (amount > 0),
    payment_method TEXT NOT NULL CHECK (payment_method IN ('Cash', 'UPI', 'Card', 'Other')),
    entry_type TEXT NOT NULL DEFAULT 'PAYMENT' CHECK (entry_type IN ('PAYMENT', 'REFUND')),
    payment_date TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (sale_id) REFERENCES sales(id)
);

-- 9. Suppliers (FR-16)
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    pincode TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 10. Supplier Purchases (FR-17, FR-20)
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_no TEXT NOT NULL UNIQUE,
    supplier_id INTEGER NOT NULL,
    supplier_invoice_no TEXT,
    total_amount NUMERIC NOT NULL DEFAULT 0.00,
    paid_amount NUMERIC NOT NULL DEFAULT 0.00,
    purchase_date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

-- 11. Purchase Line Items with Historical Cost Snapshot (FR-17, FR-21)
CREATE TABLE IF NOT EXISTS purchase_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    unit_cost NUMERIC NOT NULL CHECK (unit_cost >= 0),
    line_total NUMERIC NOT NULL CHECK (line_total >= 0),
    FOREIGN KEY (purchase_id) REFERENCES purchases(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- 12. Supplier Invoice Payments (FR-19)
CREATE TABLE IF NOT EXISTS supplier_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER NOT NULL,
    purchase_id INTEGER NOT NULL,
    amount NUMERIC NOT NULL CHECK (amount > 0),
    payment_method TEXT NOT NULL CHECK (payment_method IN ('Cash', 'UPI', 'Card', 'Other')),
    payment_date TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
    FOREIGN KEY (purchase_id) REFERENCES purchases(id)
);

-- 13. Product Returns (FR-22 to FR-25)
CREATE TABLE IF NOT EXISTS returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_no TEXT NOT NULL UNIQUE,
    sale_id INTEGER NOT NULL,
    sale_item_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC NOT NULL,
    refund_amount NUMERIC NOT NULL,
    is_resalable INTEGER NOT NULL DEFAULT 1 CHECK (is_resalable IN (0, 1)),
    settlement_type TEXT NOT NULL CHECK (settlement_type IN ('CREDIT_ADJUSTED', 'CASH_REFUND')),
    return_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (sale_id) REFERENCES sales(id),
    FOREIGN KEY (sale_item_id) REFERENCES sale_items(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- 14. Quotations (FR-26 to FR-28)
CREATE TABLE IF NOT EXISTS quotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_no TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    customer_phone TEXT,
    subtotal NUMERIC NOT NULL DEFAULT 0.00,
    discount NUMERIC NOT NULL DEFAULT 0.00,
    tax_rate NUMERIC NOT NULL DEFAULT 0.00,
    tax_amount NUMERIC NOT NULL DEFAULT 0.00,
    total_amount NUMERIC NOT NULL DEFAULT 0.00,
    status TEXT NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'Accepted', 'Rejected', 'Converted')),
    converted_sale_id INTEGER UNIQUE,
    quote_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (converted_sale_id) REFERENCES sales(id)
);

-- 15. Quotation Line Items (FR-26)
CREATE TABLE IF NOT EXISTS quotation_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quotation_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC NOT NULL CHECK (unit_price >= 0),
    line_total NUMERIC NOT NULL CHECK (line_total >= 0),
    FOREIGN KEY (quotation_id) REFERENCES quotations(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE INDEX IF NOT EXISTS idx_products_code ON products(product_code);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales(customer_id);
CREATE INDEX IF NOT EXISTS idx_purchases_supplier ON purchases(supplier_id);