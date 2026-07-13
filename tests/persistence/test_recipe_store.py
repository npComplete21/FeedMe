import pytest
from sqlalchemy import select

from app.models import Ingredient, RawSource, User
from app.parsing.recipe_parser import ParsedIngredient, ParsedRecipe
from app.persistence.recipe_store import persist_recipe


@pytest.fixture
def user(db_session):
    user = User(email="chef@example.com")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def raw_source(db_session, user):
    source = RawSource(
        user_id=user.id,
        source_url="https://youtube.com/watch?v=abc",
        source_platform="youtube",
        raw_text="today we're making fried rice with rice, eggs, and soy sauce",
    )
    db_session.add(source)
    db_session.flush()
    return source


def _parsed_recipe(**overrides) -> ParsedRecipe:
    defaults = dict(
        title="Weeknight Fried Rice",
        ingredients=[
            ParsedIngredient(name="rice", quantity="2 cups", raw_text="2 cups rice"),
            ParsedIngredient(name="eggs", quantity="2", raw_text="2 eggs"),
        ],
        steps=["Scramble the eggs", "Add rice", "Stir in soy sauce"],
    )
    defaults.update(overrides)
    return ParsedRecipe(**defaults)


def test_persist_recipe_creates_recipe_linked_to_raw_source(db_session, raw_source):
    recipe = persist_recipe(db_session, raw_source, _parsed_recipe())

    assert recipe.id is not None
    assert recipe.raw_source_id == raw_source.id
    assert recipe.user_id == raw_source.user_id
    assert recipe.source_url == raw_source.source_url
    assert recipe.source_platform == raw_source.source_platform
    assert recipe.title == "Weeknight Fried Rice"
    assert recipe.steps == ["Scramble the eggs", "Add rice", "Stir in soy sauce"]
    assert recipe.raw_source_text == raw_source.raw_text


def test_persist_recipe_creates_recipe_ingredient_links(db_session, raw_source):
    recipe = persist_recipe(db_session, raw_source, _parsed_recipe())

    names = {ri.ingredient.name for ri in recipe.ingredients}
    assert names == {"rice", "eggs"}
    quantities = {ri.ingredient.name: ri.quantity for ri in recipe.ingredients}
    assert quantities["rice"] == "2 cups"


def test_persist_recipe_normalizes_and_dedupes_ingredient_names(db_session, raw_source, user):
    persist_recipe(
        db_session,
        raw_source,
        _parsed_recipe(ingredients=[ParsedIngredient(name="Rice", raw_text="rice")]),
    )
    other_source = RawSource(
        user_id=user.id,
        source_url="https://youtube.com/watch?v=def",
        source_platform="youtube",
        raw_text="another recipe",
    )
    db_session.add(other_source)
    db_session.flush()

    persist_recipe(
        db_session,
        other_source,
        _parsed_recipe(
            title="Other Recipe",
            ingredients=[ParsedIngredient(name="  rice ", raw_text="rice")],
        ),
    )

    rice_rows = db_session.scalars(select(Ingredient).where(Ingredient.name == "rice")).all()
    assert len(rice_rows) == 1
