import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import create_access_token, hash_password, verify_password
from app.api.deps import get_db
from app.api.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.models import User

# Fails fast, same reasoning as JWT_SECRET_KEY (app/api/auth.py) - don't run
# with registration silently open to anyone. See ADR-0015.
FEEDME_REGISTRATION_CODE = os.environ.get("FEEDME_REGISTRATION_CODE")
if not FEEDME_REGISTRATION_CODE:
    raise RuntimeError(
        "FEEDME_REGISTRATION_CODE is not set. Generate one with "
        '`python -c "import secrets; print(secrets.token_hex(16))"` and add it to .env.'
    )

# Deliberately its own router, separate from app/api/routes.py's protected one -
# you can't require a valid token to log in, that's circular.
router = APIRouter(prefix="/auth")


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if payload.registration_code != FEEDME_REGISTRATION_CODE:
        raise HTTPException(status_code=403, detail="Invalid registration code")

    existing = db.scalars(select(User).where(User.email == payload.email)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalars(select(User).where(User.email == payload.email)).first()

    # Same generic error whether the email doesn't exist or the password is
    # wrong - a distinguishable error would let someone probe which emails
    # are registered.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return TokenResponse(access_token=create_access_token(user.id))
