from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Recipe
from app.persistence.recipe_queries import find_recipes
from app.persistence.recipe_store import IngredientSpec, _set_ingredients
from tests.conftest import create_test_user

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _recipe(db_session, user_id, title, *, ingredients=(), rating=None, cuisine=None, age_days=0):
    recipe = Recipe(
        user_id=user_id,
        source_url="u",
        source_platform="youtube",
        title=title,
        steps=[],
        rating=rating,
        cuisine=cuisine,
        created_at=_T0 - timedelta(days=age_days),
    )
    db_session.add(recipe)
    db_session.flush()
    _set_ingredients(db_session, recipe, [IngredientSpec(name=n) for n in ingredients])
    db_session.flush()
    return recipe


def _titles(recipes):
    return [r.title for r in recipes]


def test_default_order_is_newest_first(db_session, test_user_id):
    _recipe(db_session, test_user_id, "old", age_days=2)
    _recipe(db_session, test_user_id, "new", age_days=0)

    assert _titles(find_recipes(db_session, test_user_id)) == ["new", "old"]


def test_rating_sort_puts_best_first_and_unrated_last(db_session, test_user_id):
    _recipe(db_session, test_user_id, "unrated", age_days=0)
    _recipe(db_session, test_user_id, "three", rating=3)
    _recipe(db_session, test_user_id, "five", rating=5)
    _recipe(db_session, test_user_id, "four", rating=4)

    assert _titles(find_recipes(db_session, test_user_id, sort="rating")) == [
        "five", "four", "three", "unrated",
    ]


def test_ingredient_filter_matches_whole_words_after_normalization(db_session, test_user_id):
    _recipe(db_session, test_user_id, "plain", ingredients=["chicken"])
    _recipe(db_session, test_user_id, "thighs", ingredients=["Chicken Thighs", "rice"])
    _recipe(db_session, test_user_id, "hummus", ingredients=["chickpeas"])
    _recipe(db_session, test_user_id, "veg", ingredients=["rice"])

    found = find_recipes(db_session, test_user_id, ingredient="Chicken")
    assert sorted(_titles(found)) == ["plain", "thighs"]
    # Synonyms resolve the same way they do when recipes are saved.
    assert _titles(find_recipes(db_session, test_user_id, ingredient="garbanzo beans")) == ["hummus"]


def test_ingredient_filter_treats_input_as_text_not_regex(db_session, test_user_id):
    _recipe(db_session, test_user_id, "r", ingredients=["rice"])

    assert find_recipes(db_session, test_user_id, ingredient=".*") == []


def test_filters_combine_with_rating_sort_and_limit(db_session, test_user_id):
    _recipe(db_session, test_user_id, "k1", ingredients=["chicken"], cuisine="korean", rating=2)
    _recipe(db_session, test_user_id, "k2", ingredients=["chicken"], cuisine="korean", rating=5)
    _recipe(db_session, test_user_id, "k3", ingredients=["chicken"], cuisine="korean", rating=4)
    _recipe(db_session, test_user_id, "i1", ingredients=["chicken"], cuisine="indian", rating=5)

    found = find_recipes(
        db_session, test_user_id, ingredient="chicken", cuisine="korean", sort="rating", limit=2
    )
    assert _titles(found) == ["k2", "k3"]


def test_only_returns_the_users_own_recipes(db_session, test_user_id):
    other = create_test_user(db_session, "other@feedme.local")
    _recipe(db_session, other, "theirs", rating=5)

    assert find_recipes(db_session, test_user_id, sort="rating") == []


@pytest.mark.parametrize("rating", [0, 6])
def test_database_rejects_out_of_range_rating(db_session, test_user_id, rating):
    with pytest.raises(IntegrityError):
        _recipe(db_session, test_user_id, "bad", rating=rating)
