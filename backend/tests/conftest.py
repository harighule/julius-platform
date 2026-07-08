"""
Test fixtures for JULIUS backend tests.
"""

import atexit
import os
import sys
import pytest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

os.environ["JULIUS_DEBUG"] = "0"
os.environ["JWT_SECRET"] = "test-secret-key"
os.environ["ADMIN_DEFAULT_PASSWORD"] = "TestAdmin@1234"

# `backend.config.DB_PATH` is fixed at first import — set override before any backend package loads.
if "DB_PATH_OVERRIDE" not in os.environ:
    _test_db_f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    _test_db_f.close()
    os.environ["DB_PATH_OVERRIDE"] = _test_db_f.name

    def _cleanup_test_db_file() -> None:
        p = os.environ.get("DB_PATH_OVERRIDE")
        if p and os.path.isfile(p):
            try:
                os.unlink(p)
            except OSError:
                pass

    atexit.register(_cleanup_test_db_file)


@pytest.fixture(scope="session")
def test_db_path():
    yield os.environ["DB_PATH_OVERRIDE"]


@pytest.fixture(autouse=True)
def _reset_pantheon_mutation_rate_limits():
    from backend.services.pantheon.rate_limit import reset_pantheon_mutation_rate_limits

    reset_pantheon_mutation_rate_limits()
    yield
    reset_pantheon_mutation_rate_limits()


@pytest.fixture
def client(test_db_path):
    """Isolated SQLite file per session so schema migrations and Pantheon rows stay deterministic."""
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "TestAdmin@1234"})
    if resp.status_code != 200:
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@1234"})
    token = resp.json().get("token", "")
    return {"Authorization": f"Bearer {token}"}
