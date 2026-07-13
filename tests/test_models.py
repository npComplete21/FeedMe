import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Ingredient, Recipe, RecipeIngredient, User


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
