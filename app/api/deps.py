import os
import secrets
from collections.abc import Iterator

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import User

# Don't rely on app.main having already run load_dotenv() by the time this
# module is imported - e.g. tests import this directly. Idempotent/harmless
# to call again if it already ran.
load_dotenv()

# Phase 0-3 placeholder: single hardcoded user, get-or-created on first request.
# Every user-owned table is already scoped by user_id (ADR-0002), so swapping this
# for real auth later is a matter of deriving the id from a session/token instead.
DEFAULT_USER_EMAIL = "you@feedme.local"

# Fail fast at import time rather than silently serving unprotected requests or
# raising a confusing error on the first one - see ADR-0014.
FEEDME_API_TOKEN = os.environ.get("FEEDME_API_TOKEN")
if not FEEDME_API_TOKEN:
    raise RuntimeError(
        "FEEDME_API_TOKEN is not set. Generate one with "
        '`python -c "import secrets; print(secrets.token_hex(32))"` and add it to .env.'
    )

_bearer_scheme = HTTPBearer(auto_error=False)


def require_auth_token(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> None:
    if credentials is None or not secrets.compare_digest(credentials.credentials, FEEDME_API_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_user_id(db: Session = Depends(get_db)) -> int:
    user = db.scalars(select(User).where(User.email == DEFAULT_USER_EMAIL)).first()
    if user is None:
        user = User(email=DEFAULT_USER_EMAIL)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user.id
