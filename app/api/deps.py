from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import User

# Phase 0-3 placeholder: single hardcoded user, get-or-created on first request.
# Every user-owned table is already scoped by user_id (ADR-0002), so swapping this
# for real auth later is a matter of deriving the id from a session/token instead.
DEFAULT_USER_EMAIL = "you@feedme.local"


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
