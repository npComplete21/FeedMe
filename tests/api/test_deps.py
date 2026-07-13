from app.api.deps import DEFAULT_USER_EMAIL, get_current_user_id
from app.models import User


def test_get_current_user_id_creates_user_if_missing(db_session):
    user_id = get_current_user_id(db_session)

    user = db_session.get(User, user_id)
    assert user.email == DEFAULT_USER_EMAIL


def test_get_current_user_id_reuses_existing_user(db_session):
    first_id = get_current_user_id(db_session)
    second_id = get_current_user_id(db_session)

    assert first_id == second_id
