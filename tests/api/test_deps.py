import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.auth import create_access_token
from app.api.deps import get_current_user_id


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_get_current_user_id_decodes_a_valid_token():
    token = create_access_token(user_id=42)

    assert get_current_user_id(_bearer(token)) == 42


def test_get_current_user_id_rejects_a_malformed_token():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(_bearer("not-a-real-token"))

    assert exc_info.value.status_code == 401


def test_get_current_user_id_rejects_missing_credentials():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(None)

    assert exc_info.value.status_code == 401
