"""
test_auth.py — registration, login, sessions, and the security-
question password reset flow. Security-sensitive code gets tested
more thoroughly than average before it's ever wired into the API.

Run with: pytest tests/test_auth.py -v
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import services.auth as auth


@pytest.fixture
def isolated_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "USERS_JSON", tmp_path / "users.json")
    monkeypatch.setattr(auth, "SESSIONS_JSON", tmp_path / "sessions.json")
    monkeypatch.setattr(auth, "DATA_DIR", tmp_path)
    return auth


VALID_QUESTIONS = [
    {"question": "What city were you born in?", "answer": "Nairobi"},
    {"question": "What was your first pet's name?", "answer": "Rex"},
    {"question": "What is your mother's maiden name?", "answer": "Otieno"},
]


def test_register_success(isolated_auth):
    r = isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    assert r["success"] is True
    assert r["username"] == "deric"


def test_register_rejects_short_password(isolated_auth):
    r = isolated_auth.register("deric", "short", VALID_QUESTIONS)
    assert r["success"] is False
    assert "password" in r["reason"].lower()


def test_register_rejects_short_username(isolated_auth):
    r = isolated_auth.register("ab", "correcthorsebattery", VALID_QUESTIONS)
    assert r["success"] is False


def test_register_requires_exactly_three_questions(isolated_auth):
    r = isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS[:2])
    assert r["success"] is False
    assert "3" in r["reason"] or "questions" in r["reason"].lower()


def test_register_rejects_empty_answer(isolated_auth):
    bad = [dict(q) for q in VALID_QUESTIONS]
    bad[0]["answer"] = "   "
    r = isolated_auth.register("deric", "correcthorsebattery", bad)
    assert r["success"] is False


def test_register_rejects_duplicate_username(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    r = isolated_auth.register("deric", "anotherpassword123", VALID_QUESTIONS)
    assert r["success"] is False
    assert "taken" in r["reason"].lower()


def test_register_username_is_case_insensitive(isolated_auth):
    isolated_auth.register("Deric", "correcthorsebattery", VALID_QUESTIONS)
    r = isolated_auth.register("DERIC", "anotherpassword123", VALID_QUESTIONS)
    assert r["success"] is False


def test_password_is_never_stored_in_plaintext(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    users = isolated_auth._load_users()
    stored = users["deric"]["password_hash"]
    assert "correcthorsebattery" not in stored
    assert ":" in stored


def test_security_answers_are_never_stored_in_plaintext(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    users = isolated_auth._load_users()
    for sq in users["deric"]["security_questions"]:
        assert "nairobi" not in sq["answer_hash"].lower()
        assert "rex" not in sq["answer_hash"].lower()


def test_login_success(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    r = isolated_auth.login("deric", "correcthorsebattery")
    assert r["success"] is True
    assert "token" in r
    assert len(r["token"]) > 20


def test_login_wrong_password_fails(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    r = isolated_auth.login("deric", "wrongpassword")
    assert r["success"] is False


def test_login_nonexistent_user_fails_with_same_message_as_wrong_password(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    r1 = isolated_auth.login("deric", "wrongpassword")
    r2 = isolated_auth.login("nosuchuser", "anypassword")
    assert r1["reason"] == r2["reason"]


def test_login_is_case_insensitive_on_username(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    r = isolated_auth.login("DERIC", "correcthorsebattery")
    assert r["success"] is True


def test_verify_session_valid_token(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    login_result = isolated_auth.login("deric", "correcthorsebattery")
    r = isolated_auth.verify_session(login_result["token"])
    assert r["valid"] is True
    assert r["username"] == "deric"


def test_verify_session_rejects_garbage_token(isolated_auth):
    r = isolated_auth.verify_session("not-a-real-token")
    assert r["valid"] is False


def test_verify_session_rejects_empty_token(isolated_auth):
    r = isolated_auth.verify_session("")
    assert r["valid"] is False


def test_verify_session_rejects_expired_token(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    login_result = isolated_auth.login("deric", "correcthorsebattery")
    token = login_result["token"]

    import time
    sessions = isolated_auth._load_sessions()
    sessions[token]["expires_at"] = time.time() - 1
    isolated_auth._save_sessions(sessions)

    r = isolated_auth.verify_session(token)
    assert r["valid"] is False
    assert "expired" in r["reason"].lower()


def test_logout_invalidates_session(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    login_result = isolated_auth.login("deric", "correcthorsebattery")
    token = login_result["token"]

    assert isolated_auth.verify_session(token)["valid"] is True
    isolated_auth.logout(token)
    assert isolated_auth.verify_session(token)["valid"] is False


def test_logout_nonexistent_token_does_not_error(isolated_auth):
    r = isolated_auth.logout("token-that-never-existed")
    assert r["success"] is True


def test_get_security_questions_returns_questions_not_answers(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    r = isolated_auth.get_security_questions("deric")
    assert r["success"] is True
    assert r["questions"] == [q["question"] for q in VALID_QUESTIONS]
    assert "answer" not in str(r).lower()


def test_get_security_questions_nonexistent_user_generic_message(isolated_auth):
    r = isolated_auth.get_security_questions("nosuchuser")
    assert r["success"] is False


def test_reset_password_with_one_correct_answer_succeeds(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    r = isolated_auth.reset_password(
        "deric", answers=["wronganswer", "Rex", "wronganswer"], new_password="newpassword123",
    )
    assert r["success"] is True
    login_r = isolated_auth.login("deric", "newpassword123")
    assert login_r["success"] is True


def test_reset_password_answer_matching_is_case_insensitive(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    r = isolated_auth.reset_password(
        "deric", answers=["wrong", "  REX  ", "wrong"], new_password="newpassword123",
    )
    assert r["success"] is True


def test_reset_password_all_wrong_answers_fails(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    r = isolated_auth.reset_password(
        "deric", answers=["wrong1", "wrong2", "wrong3"], new_password="newpassword123",
    )
    assert r["success"] is False
    login_r = isolated_auth.login("deric", "correcthorsebattery")
    assert login_r["success"] is True


def test_reset_password_rejects_short_new_password(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    r = isolated_auth.reset_password("deric", answers=["x", "Rex", "x"], new_password="short")
    assert r["success"] is False


def test_reset_password_invalidates_existing_sessions(isolated_auth):
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    login_result = isolated_auth.login("deric", "correcthorsebattery")
    old_token = login_result["token"]
    assert isolated_auth.verify_session(old_token)["valid"] is True

    isolated_auth.reset_password("deric", answers=["x", "Rex", "x"], new_password="newpassword123")

    assert isolated_auth.verify_session(old_token)["valid"] is False


def test_reset_password_nonexistent_user_fails_generically(isolated_auth):
    r = isolated_auth.reset_password("nosuchuser", answers=["a", "b", "c"], new_password="newpassword123")
    assert r["success"] is False


def test_any_users_exist(isolated_auth):
    assert isolated_auth.any_users_exist() is False
    isolated_auth.register("deric", "correcthorsebattery", VALID_QUESTIONS)
    assert isolated_auth.any_users_exist() is True
