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


class InvalidTokenError(Exception):
    """Raised when a bearer token is missing, malformed, expired, or forged."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        return False
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(UTC) + timedelta(days=JWT_EXPIRATION_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(str(exc)) from exc
    return payload["user_id"]
