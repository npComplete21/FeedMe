from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from dotenv import load_dotenv

# Don't rely on app.main having already run load_dotenv() by the time this
# module is imported - e.g. tests import this directly (same reasoning as
# app/api/deps.py). Idempotent/harmless to call again if it already ran.
load_dotenv()

# See ADR-0015 for the reasoning behind these choices - JWT over sessions,
# bcrypt over rolling our own hashing, and the specific expiration window.
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is not set. Generate one with "
        '`python -c "import secrets; print(secrets.token_hex(32))"` and add it to .env.'
    )

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = int(os.environ.get("JWT_EXPIRATION_DAYS", "14"))

# Both token kinds are signed with the same secret, so the `typ` claim is what
# keeps them from being interchangeable. Without it a task token - which carries
# a user_id and deliberately never expires - would be accepted as a login token,
# i.e. a permanent credential. Each decoder below requires its own `typ`.
_ACCESS_TOKEN_TYPE = "access"
_TASK_TOKEN_TYPE = "task"


class InvalidTokenError(Exception):
    """Raised when a bearer token is missing, malformed, expired, or forged."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        return False
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _decode(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("typ") != expected_type:
        raise InvalidTokenError(f"Expected a {expected_type} token")
    return payload


def create_access_token(user_id: int) -> str:
    payload = {
        "typ": _ACCESS_TOKEN_TYPE,
        "user_id": user_id,
        "exp": datetime.now(UTC) + timedelta(days=JWT_EXPIRATION_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    return _decode(token, _ACCESS_TOKEN_TYPE)["user_id"]


def create_task_token(task_id: str, user_id: int) -> str:
    """Binds a Celery task id to the user who enqueued it.

    Celery's result backend is keyed by task id alone and has no concept of
    ownership, so the token carries its own proof rather than the API keeping a
    task -> user mapping that would have to be expired in step with Celery's own
    result expiry. Deliberately has no `exp`: it only ever grants access to a
    task the caller already owned, and the underlying result expires anyway.
    """
    payload = {"typ": _TASK_TOKEN_TYPE, "task_id": task_id, "user_id": user_id}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_task_token(token: str) -> tuple[str, int]:
    """Returns (task_id, user_id). Raises InvalidTokenError if the token is
    forged, malformed, or isn't a task token."""
    payload = _decode(token, _TASK_TOKEN_TYPE)
    task_id, user_id = payload.get("task_id"), payload.get("user_id")
    if task_id is None or user_id is None:
        raise InvalidTokenError("Task token is missing task_id or user_id")
    return task_id, user_id
