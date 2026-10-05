from sqlalchemy import select

from app.ingredients.dedup import merge_duplicate_ingredients
from app.models import Ingredient, Recipe, RecipeIngredient
from tests.conftest import create_test_user


def _recipe(db_session, user_id: int, title: str, ingredients: list[tuple[str, str | None]]) -> int:
    """Inserts ingredients by exact name, bypassing normalization - the way rows
    created before a normalization rule existed look in the real database."""
    recipe = Recipe(user_id=user_id, source_url="u", source_platform="instagram", title=title, steps=[])
    db_session.add(recipe)
    db_session.flush()
    for name, quantity in ingredients:
        ingredient = db_session.scalars(select(Ingredient).where(Ingredient.name == name)).first()
        if ingredient is None:
            ingredient = Ingredient(name=name)
            db_session.add(ingredient)
            db_session.flush()
        db_session.add(
            RecipeIngredient(recipe_id=recipe.id, ingredient_id=ingredient.id, quantity=quantity)
        )
    db_session.flush()
    return recipe.id


def _ingredients_of(db_session, recipe_id: int) -> dict[str, str | None]:
    db_session.expire_all()
    return {ri.ingredient.name: ri.quantity for ri in db_session.get(Recipe, recipe_id).ingredients}


def _all_names(db_session) -> list[str]:
    return sorted(db_session.scalars(select(Ingredient.name)).all())


def test_merges_the_real_onion_duplicates_into_one_row(db_session, test_user_id):
    a = _recipe(db_session, test_user_id, "Curry", [("onions", "2"), ("rice", "1 cup")])
    b = _recipe(db_session, test_user_id, "Salsa", [("onion (for blender)", "1")])
    c = _recipe(db_session, test_user_id, "Soup", [("onion (for cooking)", None)])

    merges = merge_duplicate_ingredients(db_session)

    assert _all_names(db_session) == ["onion", "rice"]
    assert _ingredients_of(db_session, a) == {"onion": "2", "rice": "1 cup"}
    assert _ingredients_of(db_session, b) == {"onion": "1"}
    assert _ingredients_of(db_session, c) == {"onion": None}
    [merge] = merges
    assert merge.canonical_name == "onion"


def test_prefers_the_row_already_spelled_canonically(db_session, test_user_id):
    _recipe(db_session, test_user_id, "A", [("scallions", None)])
    _recipe(db_session, test_user_id, "B", [("green onion", None)])
    canonical_id = db_session.scalars(
        select(Ingredient.id).where(Ingredient.name == "green onion")
    ).one()

    merge_duplicate_ingredients(db_session)

    assert db_session.scalars(select(Ingredient.id)).all() == [canonical_id]


def test_recipe_listing_both_spellings_keeps_one_link_and_both_quantities(
    db_session, test_user_id
):
    recipe_id = _recipe(
        db_session, test_user_id, "Double onion", [("onion", "1"), ("onions", "2 more")]
    )

    [merge] = merge_duplicate_ingredients(db_session)

    assert _ingredients_of(db_session, recipe_id) == {"onion": "1; 2 more"}
    assert merge.links_combined == 1


def test_lone_unnormalized_name_is_renamed_in_place(db_session, test_user_id):
    recipe_id = _recipe(db_session, test_user_id, "Hummus", [("Garbanzo Beans", "1 can")])

    [merge] = merge_duplicate_ingredients(db_session)

    assert _ingredients_of(db_session, recipe_id) == {"chickpea": "1 can"}
    assert merge.renamed_from == "Garbanzo Beans"


def test_is_idempotent_and_leaves_clean_data_alone(db_session, test_user_id):
    _recipe(db_session, test_user_id, "A", [("onions", None), ("rice", None)])

    assert merge_duplicate_ingredients(db_session)
    assert merge_duplicate_ingredients(db_session) == []


def test_merges_across_users_since_ingredients_are_shared(db_session, test_user_id):
    other_user = create_test_user(db_session, "other@feedme.local")
    mine = _recipe(db_session, test_user_id, "Mine", [("aubergine", None)])
    theirs = _recipe(db_session, other_user, "Theirs", [("eggplant", None)])

    merge_duplicate_ingredients(db_session)

    assert _ingredients_of(db_session, mine) == {"eggplant": None}
    assert _ingredients_of(db_session, theirs) == {"eggplant": None}
