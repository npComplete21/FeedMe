from collections.abc import Iterator

from dotenv import load_dotenv
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.auth import InvalidTokenError, decode_access_token
from app.db import SessionLocal

# Don't rely on app.main having already run load_dotenv() by the time this
# module is imported - e.g. tests import this directly. Idempotent/harmless
# to call again if it already ran.
load_dotenv()

_bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> int:
    """Both authenticates and identifies the caller in one step - the JWT itself
    proves who's asking, so there's no separate "is this request allowed at all"
    gate the way there was under the single-shared-token scheme (see ADR-0015)."""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
