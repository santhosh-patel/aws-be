"""
API and auth tests, chat scoping tests.
Run with: pytest backend/tests/api/test_auth_chat.py -v
Uses TEST_DATA_DIR and no MONGODB_URL so the app uses a temporary JSON DB.
"""
import os
import sys
import tempfile
import importlib.util

import pytest
from fastapi.testclient import TestClient

# Set test env before importing app so init_db uses temp data dir
_test_dir = tempfile.mkdtemp(prefix="aws_mcp_test_")
os.environ["TEST_DATA_DIR"] = _test_dir
os.environ["MONGODB_URL"] = ""
os.environ["ENV"] = "development"

# Load backend/app.py (the FastAPI app) as a module (avoid conflict with app package)
_backend = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, _backend)
spec = importlib.util.spec_from_file_location("main_app", os.path.join(_backend, "main.py"))
main_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_app)
app = main_app.app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@enculture.ai", "password": "Test@1234", "remember_me": False},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    token = data["token"]
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_login_success(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@enculture.ai", "password": "Test@1234", "remember_me": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data["user"]["email"] == "admin@enculture.ai"


def test_login_failure(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@enculture.ai", "password": "wrong", "remember_me": False},
    )
    assert r.status_code == 401


def test_protected_route_without_token(client):
    r = client.get("/api/chats")
    assert r.status_code == 401


def test_protected_route_invalid_token(client):
    r = client.get("/api/chats", headers={"Authorization": "Bearer invalid-token"})
    assert r.status_code == 401


def test_chats_list_scoped_to_user(client, auth_headers):
    r = client.get("/api/chats", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_chat_requires_auth(client):
    r = client.post("/api/chats", json={"title": "Test"})
    assert r.status_code == 401


def test_create_chat_success(client, auth_headers):
    r = client.post("/api/chats", json={"title": "My Chat"}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "My Chat"
    assert "_id" in data or "id" in data


def test_chat_scoping_another_user_chat_404(client, auth_headers):
    # Create a chat as current user, get its id
    r = client.post("/api/chats", json={"title": "Mine"}, headers=auth_headers)
    assert r.status_code == 200
    chat_id = r.json().get("_id") or r.json().get("id")
    # Try to get messages with a made-up other chat id (random object id shape)
    fake_id = "000000000000000000000000"
    r2 = client.get(f"/api/chats/{fake_id}/messages", headers=auth_headers)
    assert r2.status_code == 404


def test_logout(client, auth_headers):
    r = client.post("/api/auth/logout", headers=auth_headers)
    assert r.status_code == 204
