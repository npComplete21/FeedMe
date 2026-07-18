from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingredients.normalization import normalize_ingredient_name
from app.models import Ingredient, RawSource, Recipe, RecipeIngredient
from app.parsing.recipe_parser import ParsedRecipe


@dataclass
class IngredientSpec:
    name: str
    quantity: str | None = None
    raw_text: str | None = None


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


def _set_ingredients(
    session: Session, recipe: Recipe, ingredient_specs: list[IngredientSpec]
) -> None:
    """Replace a recipe's ingredient links wholesale. Used both for initial
    persistence and for edits - clearing first (rather than diffing) keeps
    "fix a bad parse" and "create from scratch" the same operation."""
    recipe.ingredients.clear()
    session.flush()

    for spec in ingredient_specs:
        ingredient = _get_or_create_ingredient(session, spec.name)
        recipe.ingredients.append(
            RecipeIngredient(
                ingredient_id=ingredient.id,
                quantity=spec.quantity,
                raw_text=spec.raw_text or spec.name,
            )
        )


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

    _set_ingredients(
        session,
        recipe,
        [
            IngredientSpec(name=i.name, quantity=i.quantity, raw_text=i.raw_text)
            for i in parsed.ingredients
        ],
    )
    session.flush()

    return recipe


def update_recipe(
    session: Session,
    recipe: Recipe,
    *,
    title: str,
    steps: list[str],
    cuisine: str | None,
    meal_type: str | None,
    cook_time_minutes: int | None,
    ingredients: list[IngredientSpec],
) -> Recipe:
    recipe.title = title
    recipe.steps = steps
    recipe.cuisine = cuisine
    recipe.meal_type = meal_type
    recipe.cook_time_minutes = cook_time_minutes

    _set_ingredients(session, recipe, ingredients)
    session.flush()

    return recipe
