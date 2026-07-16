from app.matching.ingredient_matcher import (
    MatchableIngredient,
    MatchableRecipe,
    match_recipes,
)


def _recipe(id: int, title: str, *ingredient_names: str) -> MatchableRecipe:
    return MatchableRecipe(
        id=id,
        title=title,
        ingredients=[MatchableIngredient(name=n) for n in ingredient_names],
    )


def test_exact_match_has_ratio_one_and_no_missing():
    recipe = _recipe(1, "Fried Rice", "rice", "eggs", "soy sauce")

    [result] = match_recipes(["rice", "eggs", "soy sauce"], [recipe])

    assert result.match_ratio == 1.0
    assert result.missing_ingredients == []
    assert set(result.matched_ingredients) == {"rice", "eggs", "soy sauce"}


def test_empty_pantry_matches_nothing():
    recipe = _recipe(1, "Fried Rice", "rice", "eggs")

    [result] = match_recipes([], [recipe])

    assert result.match_ratio == 0.0
    assert result.matched_ingredients == []
    assert set(result.missing_ingredients) == {"rice", "eggs"}


def test_partial_match_lists_missing_ingredients():
    recipe = _recipe(1, "Fried Rice", "rice", "eggs")

    [result] = match_recipes(["rice"], [recipe])

    assert result.match_ratio == 0.5
    assert result.matched_ingredients == ["rice"]
    assert result.missing_ingredients == ["eggs"]


def test_normalization_is_case_and_whitespace_insensitive():
    recipe = _recipe(1, "Fried Rice", "rice", "eggs")

    [result] = match_recipes([" Rice ", "EGGS"], [recipe])

    assert result.match_ratio == 1.0
    assert result.missing_ingredients == []


def test_results_sorted_by_match_ratio_descending():
    full_match = _recipe(1, "Full Match", "rice")
    half_match = _recipe(2, "Half Match", "rice", "eggs")
    no_match = _recipe(3, "No Match", "chicken")

    results = match_recipes(["rice"], [half_match, no_match, full_match])

    assert [r.recipe.title for r in results] == ["Full Match", "Half Match", "No Match"]


def test_ties_broken_alphabetically_by_title():
    zucchini = _recipe(1, "Zucchini Bread", "flour", "zucchini")
    apple = _recipe(2, "Apple Pie", "flour", "apples")

    results = match_recipes(["flour"], [zucchini, apple])

    assert [r.recipe.title for r in results] == ["Apple Pie", "Zucchini Bread"]


def test_synonyms_and_prep_notes_match_a_plain_pantry_item():
    # the real bug: a recipe ingredient phrased as "onion (for cooking)" should
    # still match a pantry that just says "onion"
    recipe = _recipe(1, "Bibimbap", "onion (for cooking)", "green onion")

    [result] = match_recipes(["onion", "scallion"], [recipe])

    assert result.match_ratio == 1.0
    assert result.missing_ingredients == []


def test_recipe_with_no_ingredients_ranks_below_zero_ratio_recipe_with_real_ingredients():
    empty = _recipe(1, "Empty Recipe")
    unmatched = _recipe(2, "Unmatched Recipe", "durian")

    results = match_recipes(["rice"], [empty, unmatched])

    assert results[0].recipe.title == "Unmatched Recipe"
    assert results[1].recipe.title == "Empty Recipe"
    assert results[1].match_ratio == 0.0
    assert results[1].missing_ingredients == []
