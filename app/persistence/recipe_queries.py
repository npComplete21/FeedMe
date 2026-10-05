import re
from typing import Literal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.ingredients.normalization import normalize_ingredient_name
from app.models import Ingredient, Recipe, RecipeIngredient

RecipeSort = Literal["newest", "rating"]


def find_recipes(
    session: Session,
    user_id: int,
    *,
    cuisine: str | None = None,
    meal_type: str | None = None,
    max_cook_time_minutes: int | None = None,
    ingredient: str | None = None,
    sort: RecipeSort = "newest",
    limit: int | None = None,
) -> list[Recipe]:
    """One user's recipes, filtered and ordered. Shared by GET /recipes and the
    chat assistant's tool, so "my best chicken recipes" means the same thing in
    both places (ADR-0028).

    `ingredient` matches whole words of a normalized ingredient name, so
    "chicken" finds "chicken" and "chicken thighs" but not "chickpea".
    `sort="rating"` puts the highest-rated first and unrated recipes last.
    """
    query = select(Recipe).where(Recipe.user_id == user_id)
    if cuisine is not None:
        query = query.where(Recipe.cuisine == cuisine)
    if meal_type is not None:
        query = query.where(Recipe.meal_type == meal_type)
    if max_cook_time_minutes is not None:
        query = query.where(Recipe.cook_time_minutes <= max_cook_time_minutes)
    if ingredient is not None and (name := normalize_ingredient_name(ingredient)):
        # \m and \M are Postgres's start/end-of-word anchors.
        pattern = rf"\m{re.escape(name)}\M"
        query = query.where(
            exists()
            .where(RecipeIngredient.recipe_id == Recipe.id)
            .where(RecipeIngredient.ingredient_id == Ingredient.id)
            .where(Ingredient.name.regexp_match(pattern))
        )

    if sort == "rating":
        query = query.order_by(Recipe.rating.desc().nulls_last(), Recipe.created_at.desc())
    else:
        query = query.order_by(Recipe.created_at.desc())
    if limit is not None:
        query = query.limit(limit)

    return list(session.scalars(query).all())
