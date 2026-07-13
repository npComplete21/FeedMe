import pytest

from app.ingestion.pipeline import ingest_manual_caption, ingest_youtube
from app.ingestion.youtube import YouTubeSource
from app.models import RawSource, User
from app.parsing.recipe_parser import ParsedIngredient, ParsedRecipe


@pytest.fixture
def user(db_session):
    user = User(email="chef@example.com")
    db_session.add(user)
    db_session.flush()
    return user


def _parsed_recipe() -> ParsedRecipe:
    return ParsedRecipe(
        title="Weeknight Fried Rice",
        ingredients=[ParsedIngredient(name="rice", quantity="2 cups", raw_text="2 cups rice")],
        steps=["Cook rice", "Stir fry"],
    )


def test_ingest_youtube_orchestrates_fetch_parse_and_persist(monkeypatch, db_session, user):
    fake_source = YouTubeSource(
        source_url="https://youtube.com/watch?v=abc",
        title="Fried Rice Video",
        channel="Cooking Channel",
        thumbnail_url="https://example.com/thumb.jpg",
        transcript_text="today we make fried rice with rice, soy sauce",
    )
    monkeypatch.setattr(
        "app.ingestion.pipeline.fetch_youtube_transcript", lambda url: fake_source
    )
    monkeypatch.setattr(
        "app.ingestion.pipeline.parse_recipe", lambda raw_text: _parsed_recipe()
    )

    recipe = ingest_youtube(db_session, user.id, "https://youtube.com/watch?v=abc")

    assert recipe.id is not None
    assert recipe.user_id == user.id
    assert recipe.title == "Weeknight Fried Rice"
    assert recipe.source_platform == "youtube"
    assert recipe.raw_source_id is not None

    raw_source = db_session.get(RawSource, recipe.raw_source_id)
    assert raw_source.raw_text == fake_source.transcript_text
    assert raw_source.title == "Fried Rice Video"


def test_ingest_manual_caption_orchestrates_save_parse_and_persist(monkeypatch, db_session, user):
    monkeypatch.setattr(
        "app.ingestion.pipeline.parse_recipe", lambda raw_text: _parsed_recipe()
    )

    recipe = ingest_manual_caption(
        db_session,
        user.id,
        "https://instagram.com/reel/abc123",
        "1 cup rice, 2 eggs, soy sauce",
    )

    assert recipe.user_id == user.id
    assert recipe.source_platform == "instagram"
    assert recipe.title == "Weeknight Fried Rice"

    raw_source = db_session.get(RawSource, recipe.raw_source_id)
    assert raw_source.raw_text == "1 cup rice, 2 eggs, soy sauce"


def test_ingest_youtube_propagates_parse_failures(monkeypatch, db_session, user):
    from app.parsing.recipe_parser import RecipeParseError

    fake_source = YouTubeSource(
        source_url="https://youtube.com/watch?v=abc",
        title="Video",
        channel=None,
        thumbnail_url=None,
        transcript_text="not a recipe",
    )
    monkeypatch.setattr(
        "app.ingestion.pipeline.fetch_youtube_transcript", lambda url: fake_source
    )

    def _raise(raw_text):
        raise RecipeParseError("declined")

    monkeypatch.setattr("app.ingestion.pipeline.parse_recipe", _raise)

    with pytest.raises(RecipeParseError):
        ingest_youtube(db_session, user.id, "https://youtube.com/watch?v=abc")
