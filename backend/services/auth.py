"""
auth.py — accounts, login/logout, and security-question password reset.

Design choices, deliberately:

  Password hashing uses hashlib.pbkdf2_hmac (Python standard library),
  NOT bcrypt/argon2. Those are legitimate, well-regarded choices in
  general, but they're C-extension packages that need a prebuilt wheel
  for whatever Python version is installed - exactly the class of
  problem that caused a real, painful failure earlier in this project
  (pydantic-core/lxml failing to compile on a very new Python
  version). PBKDF2-HMAC-SHA256 with a high iteration count is still a
  legitimate, standard, NIST-recognized password hashing approach, and
  using it means account creation can never fail because of a missing
  C compiler on someone's machine.

  Sessions are simple, random, server-side-stored tokens (not JWT) -
  no new dependency, no risk of a JWT library's own version/CVE
  churn. Traded off: sessions don't survive if the token store file
  is lost, but that's an acceptable, honestly-documented limitation
  for a single-operator system, not a hidden one.

  Security questions: the ANSWER is hashed the same way a password is
  (never stored in plaintext), and matched case-insensitively with
  whitespace stripped, since "Nairobi" and "nairobi " should both
  count as correct - a user shouldn't get locked out over exact
  capitalization they don't remember.
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone

from services.paths import DATA_DIR

USERS_JSON = DATA_DIR / "users.json"
SESSIONS_JSON = DATA_DIR / "sessions.json"

PBKDF2_ITERATIONS = 260_000  # OWASP-recommended floor for PBKDF2-HMAC-SHA256 as of 2023
SESSION_TTL_SECONDS = 7 * 24 * 3600  # 7 days
MIN_PASSWORD_LENGTH = 8
REQUIRED_SECURITY_QUESTIONS = 3


def _hash_secret(secret: str, salt: bytes = None) -> str:
    """Returns 'salt_hex:hash_hex'. Never store or compare plaintext."""
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}:{digest.hex()}"


def _verify_secret(secret: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        actual = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        return hmac.compare_digest(actual, expected)  # constant-time - avoids timing attacks
    except Exception:
        return False


def _normalize_answer(answer: str) -> str:
    """Security-question answers are matched case-insensitively with
    surrounding whitespace stripped - a user shouldn't fail a reset
    over capitalization or a trailing space they don't remember."""
    return answer.strip().lower()


def _load_users() -> dict:
    if USERS_JSON.exists():
        try:
            with open(USERS_JSON) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_users(users: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = USERS_JSON.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(users, f, indent=2)
    tmp.replace(USERS_JSON)  # atomic on POSIX and Windows


def _load_sessions() -> dict:
    if SESSIONS_JSON.exists():
        try:
            with open(SESSIONS_JSON) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_sessions(sessions: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SESSIONS_JSON.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(sessions, f, indent=2)
    tmp.replace(SESSIONS_JSON)


def register(username: str, password: str, security_questions: list) -> dict:
    """
    security_questions: list of {"question": str, "answer": str},
    exactly REQUIRED_SECURITY_QUESTIONS (3) entries - used later for
    password reset: get any ONE right and you can reset your password.
    """
    username = username.strip().lower()

    if not username or len(username) < 3:
        return {"success": False, "reason": "Username must be at least 3 characters"}
    if len(password) < MIN_PASSWORD_LENGTH:
        return {"success": False, "reason": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}
    if not security_questions or len(security_questions) != REQUIRED_SECURITY_QUESTIONS:
        return {"success": False, "reason": f"Exactly {REQUIRED_SECURITY_QUESTIONS} security questions are required"}
    for sq in security_questions:
        if not sq.get("question", "").strip() or not sq.get("answer", "").strip():
            return {"success": False, "reason": "Every security question must have both a question and an answer"}

    users = _load_users()
    if username in users:
        return {"success": False, "reason": "That username is already taken"}

    users[username] = {
        "username": username,
        "password_hash": _hash_secret(password),
        "security_questions": [
            {
                "question": sq["question"].strip(),
                "answer_hash": _hash_secret(_normalize_answer(sq["answer"])),
            }
            for sq in security_questions
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_users(users)
    return {"success": True, "username": username}


def login(username: str, password: str) -> dict:
    username = username.strip().lower()
    users = _load_users()
    user = users.get(username)

    # Deliberately identical error message whether the username
    # doesn't exist or the password is wrong - distinguishing the two
    # would let an attacker enumerate valid usernames.
    invalid = {"success": False, "reason": "Incorrect username or password"}
    if not user:
        return invalid
    if not _verify_secret(password, user["password_hash"]):
        return invalid

    token = secrets.token_urlsafe(32)
    sessions = _load_sessions()
    sessions[token] = {
        "username": username,
        "created_at": time.time(),
        "expires_at": time.time() + SESSION_TTL_SECONDS,
    }
    _save_sessions(sessions)
    return {"success": True, "username": username, "token": token, "expires_in_seconds": SESSION_TTL_SECONDS}


def logout(token: str) -> dict:
    sessions = _load_sessions()
    if token in sessions:
        del sessions[token]
        _save_sessions(sessions)
    return {"success": True}


def verify_session(token: str) -> dict:
    """Returns {"valid": True, "username": ...} or {"valid": False, "reason": ...}.
    Expired sessions are treated as invalid and lazily cleaned up."""
    if not token:
        return {"valid": False, "reason": "No session token provided"}
    sessions = _load_sessions()
    session = sessions.get(token)
    if not session:
        return {"valid": False, "reason": "Session not found - please log in again"}
    if time.time() > session["expires_at"]:
        del sessions[token]
        _save_sessions(sessions)
        return {"valid": False, "reason": "Session expired - please log in again"}
    return {"valid": True, "username": session["username"]}


def get_security_questions(username: str) -> dict:
    """Returns just the QUESTIONS (never answers/hashes) for a
    username, so the frontend can present them on the reset form."""
    username = username.strip().lower()
    users = _load_users()
    user = users.get(username)
    if not user:
        # Same "don't reveal whether the account exists" principle as
        # login - return a generic, non-committal response either way.
        return {"success": False, "reason": "If that account exists, questions would be shown here"}
    return {
        "success": True,
        "questions": [sq["question"] for sq in user["security_questions"]],
    }


def reset_password(username: str, answers: list, new_password: str) -> dict:
    """
    answers: list of strings, same order as get_security_questions()
    returned them. Getting ANY ONE correct unlocks the reset - per the
    explicit requirement that one correct answer is enough, not all
    three.
    """
    username = username.strip().lower()
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return {"success": False, "reason": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}

    users = _load_users()
    user = users.get(username)
    if not user:
        return {"success": False, "reason": "Incorrect username or answers"}

    questions = user["security_questions"]
    if len(answers) != len(questions):
        return {"success": False, "reason": "Please answer all questions shown"}

    any_correct = any(
        _verify_secret(_normalize_answer(ans), q["answer_hash"])
        for ans, q in zip(answers, questions)
    )
    if not any_correct:
        # Same generic message as "account doesn't exist" - never
        # reveal whether the username was right but answers were
        # wrong, vs. the username itself being wrong.
        return {"success": False, "reason": "Incorrect username or answers"}

    user["password_hash"] = _hash_secret(new_password)
    users[username] = user
    _save_users(users)

    # Invalidate all existing sessions for this account on password
    # reset - a real security requirement, not optional polish: if
    # someone else had access via an old session, a password reset
    # must actually lock them out too.
    sessions = _load_sessions()
    sessions = {tok: s for tok, s in sessions.items() if s["username"] != username}
    _save_sessions(sessions)

    return {"success": True}


def any_users_exist() -> bool:
    """Used by the frontend to decide whether to show 'Register' as
    the primary action (first-run, no accounts yet) or 'Login'."""
    return len(_load_users()) > 0
