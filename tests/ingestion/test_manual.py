import pytest
from sqlalchemy import select

from app.ingestion.manual import EmptyCaptionError, EmptySourceUrlError, save_manual_caption
from app.models import RawSource, User


@pytest.fixture
def user(db_session):
    user = User(email="chef@example.com")
    db_session.add(user)
    db_session.flush()
    return user


def test_save_manual_caption_persists_and_is_retrievable(db_session, user):
    saved = save_manual_caption(
        db_session,
        user_id=user.id,
        source_url="https://instagram.com/reel/abc123",
        caption_text="1 cup rice, 2 eggs, soy sauce. Fry it all together.",
    )

    fetched = db_session.get(RawSource, saved.id)
    assert fetched.user_id == user.id
    assert fetched.source_url == "https://instagram.com/reel/abc123"
    assert fetched.raw_text == "1 cup rice, 2 eggs, soy sauce. Fry it all together."


def test_save_manual_caption_defaults_to_instagram_platform(db_session, user):
    saved = save_manual_caption(
        db_session,
        user_id=user.id,
        source_url="https://instagram.com/reel/abc123",
        caption_text="some caption",
    )

    assert saved.source_platform == "instagram"


def test_save_manual_caption_strips_whitespace(db_session, user):
    saved = save_manual_caption(
        db_session,
        user_id=user.id,
        source_url="  https://instagram.com/reel/abc123  ",
        caption_text="  some caption  ",
    )

    assert saved.source_url == "https://instagram.com/reel/abc123"
    assert saved.raw_text == "some caption"


def test_save_manual_caption_rejects_empty_caption(db_session, user):
    with pytest.raises(EmptyCaptionError):
        save_manual_caption(
            db_session,
            user_id=user.id,
            source_url="https://instagram.com/reel/abc123",
            caption_text="   ",
        )

    assert db_session.scalars(select(RawSource).where(RawSource.user_id == user.id)).first() is None


def test_save_manual_caption_rejects_empty_url(db_session, user):
    with pytest.raises(EmptySourceUrlError):
        save_manual_caption(
            db_session,
            user_id=user.id,
            source_url="   ",
            caption_text="some caption",
        )

    assert db_session.scalars(select(RawSource).where(RawSource.user_id == user.id)).first() is None
