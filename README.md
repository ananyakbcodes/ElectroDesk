# ElectroDesk — Electrical Retail Management and Inventory Intelligence System

ElectroDesk is a local-first web application built with **Python, Flask, and SQLite** to digitize counter billing, inventory management (including decimal wire lengths), customer credit ledgers, supplier purchases, product returns, quotations, operational reports, and database backups for an electrical retail store.

Developed following the **Waterfall SDLC methodology** for the Software Engineering course at **Goa Business School, Goa University**.

## Project Architecture
- `app.py` / `config.py` — Flask application factory, startup daily backup hook, and configuration.
- `database/` — Relational SQLite schema (`schema.sql`), WAL/Foreign-Key connection manager (`db.py`), and demo seed script (`seed.py`).
- `services/` — Modular business logic (`inventory_service`, `billing_service`, `purchase_service`, `return_service`, `quotation_service`, `report_service`, `backup_service`, `external_api`).
- `routes/` — HTTP blueprints and JSON REST API endpoints (`/api/products`, `/api/sales`, `/api/summary`).
- `templates/` & `static/` — Jinja2 HTML screens and print-ready invoice stylesheets.
- `tests/` — Automated Pytest unit, functional, API, backup-restore, and performance tests.
- `.github/workflows/ci.yml` — Continuous Integration pipeline via GitHub Actions.

## Quick Setup & Run (Windows)
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py