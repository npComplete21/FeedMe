from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingredients.normalization import normalize_ingredient_name
from app.models import Ingredient, RawSource, Recipe, RecipeIngredient
from app.parsing.recipe_parser import ParsedRecipe


def _get_or_create_ingredient(session: Session, name: str) -> Ingredient:
    normalized = normalize_ingredient_name(name)
    ingredient = session.scalars(
        select(Ingredient).where(Ingredient.name == normalized)
    ).first()
    if ingredient is None:
        ingredient = Ingredient(name=normalized)
        session.add(ingredient)
        session.flush()
    return ingredient


def persist_recipe(session: Session, raw_source: RawSource, parsed: ParsedRecipe) -> Recipe:
    recipe = Recipe(
        user_id=raw_source.user_id,
        raw_source_id=raw_source.id,
        source_url=raw_source.source_url,
        source_platform=raw_source.source_platform,
        title=parsed.title,
        steps=parsed.steps,
        cuisine=parsed.cuisine,
        meal_type=parsed.meal_type,
        cook_time_minutes=parsed.cook_time_minutes,
        raw_source_text=raw_source.raw_text,
    )
    session.add(recipe)
    session.flush()

    for parsed_ingredient in parsed.ingredients:
        ingredient = _get_or_create_ingredient(session, parsed_ingredient.name)
        session.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                quantity=parsed_ingredient.quantity,
                raw_text=parsed_ingredient.raw_text,
            )
        )
    session.flush()

    return recipe
