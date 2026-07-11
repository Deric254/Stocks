"""
test_auth_api.py — API-level tests for the auth endpoints (register,
login, logout, me, forgot-password). Uses isolated user/session
storage so real accounts are never touched by test runs.

Run with: pytest tests/test_auth_api.py -v
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app
    import services.auth as auth_module
    monkeypatch.setattr(auth_module, "USERS_JSON", tmp_path / "users.json")
    monkeypatch.setattr(auth_module, "SESSIONS_JSON", tmp_path / "sessions.json")
    from fastapi.testclient import TestClient
    return TestClient(app.app)


VALID_QUESTIONS = [
    {"question": "City born in?", "answer": "Nairobi"},
    {"question": "First pet?", "answer": "Rex"},
    {"question": "Mother's maiden name?", "answer": "Otieno"},
]


def _register(client, username="deric", password="correcthorsebattery"):
    return client.post("/api/auth/register", json={
        "username": username, "password": password, "security_questions": VALID_QUESTIONS,
    })


def test_full_register_login_me_flow(client):
    r = _register(client)
    assert r.status_code == 200

    r = client.post("/api/auth/login", json={"username": "deric", "password": "correcthorsebattery"})
    assert r.status_code == 200
    token = r.json()["token"]

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "deric"


def test_me_without_token_is_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_garbage_token_is_401(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage-token"})
    assert r.status_code == 401


def test_login_wrong_password_is_401(client):
    _register(client)
    r = client.post("/api/auth/login", json={"username": "deric", "password": "wrongpassword"})
    assert r.status_code == 401


def test_register_duplicate_username_is_400(client):
    _register(client)
    r = _register(client)
    assert r.status_code == 400


def test_register_missing_fields_is_422(client):
    r = client.post("/api/auth/register", json={"username": "deric"})
    assert r.status_code == 422


def test_logout_then_me_is_401(client):
    _register(client)
    r = client.post("/api/auth/login", json={"username": "deric", "password": "correcthorsebattery"})
    token = r.json()["token"]

    r2 = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200

    r3 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r3.status_code == 401


def test_forgot_password_full_flow(client):
    _register(client)

    r = client.get("/api/auth/security-questions/deric")
    assert r.status_code == 200
    assert len(r.json()["questions"]) == 3

    r2 = client.post("/api/auth/reset-password", json={
        "username": "deric", "answers": ["wrong", "Rex", "wrong"], "new_password": "newpassword123",
    })
    assert r2.status_code == 200

    r3 = client.post("/api/auth/login", json={"username": "deric", "password": "newpassword123"})
    assert r3.status_code == 200

    r4 = client.post("/api/auth/login", json={"username": "deric", "password": "correcthorsebattery"})
    assert r4.status_code == 401


def test_forgot_password_all_wrong_answers_is_400(client):
    _register(client)
    r = client.post("/api/auth/reset-password", json={
        "username": "deric", "answers": ["wrong", "wrong", "wrong"], "new_password": "newpassword123",
    })
    assert r.status_code == 400


def test_auth_status_reflects_registration(client):
    r = client.get("/api/auth/status")
    assert r.json()["any_users_exist"] is False
    _register(client)
    r2 = client.get("/api/auth/status")
    assert r2.json()["any_users_exist"] is True


def test_security_questions_for_unknown_user_is_404(client):
    r = client.get("/api/auth/security-questions/nosuchuser")
    assert r.status_code == 404
