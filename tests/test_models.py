import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.models import Ingredient, RawSource, Recipe, RecipeIngredient, User


def test_create_user_and_recipe(db_session):
    user = User(email="chef@example.com")
    db_session.add(user)
    db_session.flush()

    recipe = Recipe(
        user_id=user.id,
        source_url="https://youtube.com/watch?v=abc",
        source_platform="youtube",
        title="Weeknight Fried Rice",
        steps=["Cook rice", "Stir fry vegetables", "Combine"],
    )
    db_session.add(recipe)
    db_session.flush()

    fetched = db_session.get(Recipe, recipe.id)
    assert fetched.user_id == user.id
    assert fetched.steps == ["Cook rice", "Stir fry vegetables", "Combine"]


def test_recipe_ingredient_links_recipe_and_ingredient(db_session):
    user = User(email="chef2@example.com")
    db_session.add(user)
    db_session.flush()

    recipe = Recipe(
        user_id=user.id,
        source_url="https://youtube.com/watch?v=def",
        source_platform="youtube",
        title="Garlic Noodles",
        steps=["Boil noodles", "Toss with garlic sauce"],
    )
    ingredient = Ingredient(name="garlic")
    db_session.add_all([recipe, ingredient])
    db_session.flush()

    link = RecipeIngredient(
        recipe_id=recipe.id,
        ingredient_id=ingredient.id,
        quantity="3 cloves",
        raw_text="3 cloves garlic, minced",
    )
    db_session.add(link)
    db_session.flush()

    assert recipe.ingredients[0].ingredient.name == "garlic"


def test_recipe_ingredient_rejects_nonexistent_recipe(db_session):
    ingredient = Ingredient(name="salt")
    db_session.add(ingredient)
    db_session.flush()

    db_session.add(RecipeIngredient(recipe_id=999_999, ingredient_id=ingredient.id))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_user_email_rejected(db_session):
    db_session.add(User(email="dup@example.com"))
    db_session.flush()

    db_session.add(User(email="dup@example.com"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def _user_with_recipe(db_session, email: str) -> tuple[int, int, int]:
    """Returns (user_id, recipe_id, ingredient_id) - plain ids, since the ORM
    objects themselves become unusable once their rows are cascade-deleted."""
    user = User(email=email)
    db_session.add(user)
    db_session.flush()
    raw = RawSource(user_id=user.id, source_url="u", source_platform="instagram", raw_text="t")
    db_session.add(raw)
    db_session.flush()
    recipe = Recipe(
        user_id=user.id,
        raw_source_id=raw.id,
        source_url="u",
        source_platform="instagram",
        title="Toast",
        steps=["Toast it"],
    )
    ingredient = Ingredient(name=f"bread-{email}")
    db_session.add_all([recipe, ingredient])
    db_session.flush()
    db_session.add(RecipeIngredient(recipe_id=recipe.id, ingredient_id=ingredient.id))
    db_session.flush()
    return user.id, recipe.id, ingredient.id


def _counts(db_session, user_id: int, recipe_id: int) -> tuple[int, int, int]:
    return (
        len(db_session.scalars(select(Recipe).where(Recipe.user_id == user_id)).all()),
        len(db_session.scalars(select(RawSource).where(RawSource.user_id == user_id)).all()),
        len(
            db_session.scalars(
                select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe_id)
            ).all()
        ),
    )


def test_sql_delete_of_user_cascades_to_owned_rows(db_session):
    user_id, recipe_id, ingredient_id = _user_with_recipe(db_session, "cascade-sql@example.com")

    db_session.execute(delete(User).where(User.id == user_id))
    db_session.expire_all()

    assert _counts(db_session, user_id, recipe_id) == (0, 0, 0)
    # Shared lookup table - outlives the user by design.
    assert db_session.get(Ingredient, ingredient_id) is not None


def test_orm_delete_of_user_cascades_to_owned_rows(db_session):
    user_id, recipe_id, _ = _user_with_recipe(db_session, "cascade-orm@example.com")

    # The obvious "delete my account" implementation - must not raise.
    db_session.delete(db_session.get(User, user_id))
    db_session.flush()
    db_session.expire_all()

    assert _counts(db_session, user_id, recipe_id) == (0, 0, 0)


def test_deleting_raw_source_keeps_recipe(db_session):
    _, recipe_id, _ = _user_with_recipe(db_session, "raw-null@example.com")
    raw_source_id = db_session.get(Recipe, recipe_id).raw_source_id

    db_session.execute(delete(RawSource).where(RawSource.id == raw_source_id))
    db_session.expire_all()

    assert db_session.get(Recipe, recipe_id).raw_source_id is None


def test_deleting_ingredient_in_use_is_rejected(db_session):
    _, _, ingredient_id = _user_with_recipe(db_session, "ingredient-restrict@example.com")

    with pytest.raises(IntegrityError):
        db_session.execute(delete(Ingredient).where(Ingredient.id == ingredient_id))
