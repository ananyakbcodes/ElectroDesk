import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("ELECTRODESK_SECRET_KEY", "electrodesk-local-store-secret-2026")
    DB_PATH = os.environ.get("ELECTRODESK_DB_PATH", os.path.join(BASE_DIR, "electrodesk.db"))
    BACKUP_DIR = os.environ.get("ELECTRODESK_BACKUP_DIR", os.path.join(BASE_DIR, "backups"))
    INTERNAL_API_KEY = os.environ.get("ELECTRODESK_API_KEY", "electrodesk-api-key-2026")
    DEFAULT_ADMIN_USER = "admin"
    DEFAULT_ADMIN_PASS = "admin123"