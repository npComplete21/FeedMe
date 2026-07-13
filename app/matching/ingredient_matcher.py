from dataclasses import dataclass


def _normalize(name: str) -> str:
    return name.strip().lower()


@dataclass
class MatchableIngredient:
    name: str


@dataclass
class MatchableRecipe:
    id: int
    title: str
    ingredients: list[MatchableIngredient]


@dataclass
class RecipeMatch:
    recipe: MatchableRecipe
    matched_ingredients: list[str]
    missing_ingredients: list[str]
    match_ratio: float


def match_recipes(pantry: list[str], recipes: list[MatchableRecipe]) -> list[RecipeMatch]:
    """Rank recipes by how many of their ingredients are covered by the pantry.

    A recipe with zero ingredients has a match_ratio of 0.0 rather than a vacuous
    1.0 - it carries no matching signal, so it should rank last, not first.
    """
    pantry_set = {_normalize(item) for item in pantry}

    matches = []
    for recipe in recipes:
        matched = []
        missing = []
        for ingredient in recipe.ingredients:
            if _normalize(ingredient.name) in pantry_set:
                matched.append(ingredient.name)
            else:
                missing.append(ingredient.name)

        total = len(recipe.ingredients)
        match_ratio = len(matched) / total if total else 0.0

        matches.append(
            RecipeMatch(
                recipe=recipe,
                matched_ingredients=matched,
                missing_ingredients=missing,
                match_ratio=match_ratio,
            )
        )

    return sorted(
        matches,
        key=lambda m: (
            -m.match_ratio,
            len(m.recipe.ingredients) == 0,  # push zero-ingredient recipes to the bottom
            len(m.missing_ingredients),
            m.recipe.title,
        ),
    )
