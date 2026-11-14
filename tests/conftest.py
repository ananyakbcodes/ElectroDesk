import pytest
from app import create_app
from config import Config
from database.db import init_db


@pytest.fixture
def temp_db(tmp_path):
    """Provide an isolated temporary SQLite database per test."""
    db_file = tmp_path / "test_electrodesk.db"
    init_db(db_path=str(db_file))
    return str(db_file)


@pytest.fixture
def temp_backup_dir(tmp_path):
    bdir = tmp_path / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    return str(bdir)


@pytest.fixture
def client(temp_db, temp_backup_dir):
    """Provide a Flask test client backed by the temporary database."""
    app = create_app(
        {
            "TESTING": True,
            "DB_PATH": temp_db,
            "BACKUP_DIR": temp_backup_dir,
            "SECRET_KEY": "test-secret-key",
        }
    )
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def auth_client(client):
    """Provide an already logged-in operator Flask test client."""
    client.post(
        "/login",
        data={"username": Config.DEFAULT_ADMIN_USER, "password": Config.DEFAULT_ADMIN_PASS},
        follow_redirects=True,
    )
    return client