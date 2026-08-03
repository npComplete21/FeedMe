from app.api.schemas import IngredientResponse, RecipeResponse
from app.models import Recipe


def recipe_to_response(recipe: Recipe) -> RecipeResponse:
    return RecipeResponse(
        id=recipe.id,
        title=recipe.title,
        source_url=recipe.source_url,
        source_platform=recipe.source_platform,
        steps=recipe.steps,
        ingredients=[
            IngredientResponse(name=ri.ingredient.name, quantity=ri.quantity)
            for ri in recipe.ingredients
        ],
        cuisine=recipe.cuisine,
        meal_type=recipe.meal_type,
        cook_time_minutes=recipe.cook_time_minutes,
        created_at=recipe.created_at,
    )
