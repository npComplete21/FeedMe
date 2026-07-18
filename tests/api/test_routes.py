from app.api.deps import get_current_user_id
from app.models import Ingredient, Recipe, RecipeIngredient


def _make_recipe(
    db_session,
    user_id,
    title="Fried Rice",
    ingredients=None,
    cuisine=None,
    meal_type=None,
    cook_time_minutes=None,
):
    recipe = Recipe(
        user_id=user_id,
        source_url="https://youtube.com/watch?v=abc",
        source_platform="youtube",
        title=title,
        steps=["step"],
        cuisine=cuisine,
        meal_type=meal_type,
        cook_time_minutes=cook_time_minutes,
    )
    db_session.add(recipe)
    db_session.flush()
    for name in ingredients or []:
        ingredient = Ingredient(name=name)
        db_session.add(ingredient)
        db_session.flush()
        db_session.add(RecipeIngredient(recipe_id=recipe.id, ingredient_id=ingredient.id))
    db_session.flush()
    return recipe


def test_ingest_recipe_youtube_returns_created_recipe(client, monkeypatch):
    def fake_ingest_youtube(db, user_id, url):
        return _make_recipe(db, user_id, title="Fried Rice")

    monkeypatch.setattr("app.api.routes.ingest_youtube", fake_ingest_youtube)

    response = client.post(
        "/recipes/ingest",
        json={"source_platform": "youtube", "url": "https://youtube.com/watch?v=abc"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Fried Rice"
    assert body["source_platform"] == "youtube"


def test_ingest_recipe_manual_requires_caption_text(client):
    response = client.post(
        "/recipes/ingest",
        json={"source_platform": "instagram", "url": "https://instagram.com/reel/abc"},
    )

    assert response.status_code == 422


def test_ingest_recipe_manual_calls_manual_pipeline(client, monkeypatch):
    captured = {}

    def fake_ingest_manual_caption(db, user_id, url, caption_text, source_platform="instagram"):
        captured["caption_text"] = caption_text
        return _make_recipe(db, user_id, title="Manual Recipe")

    monkeypatch.setattr("app.api.routes.ingest_manual_caption", fake_ingest_manual_caption)

    response = client.post(
        "/recipes/ingest",
        json={
            "source_platform": "instagram",
            "url": "https://instagram.com/reel/abc",
            "caption_text": "1 cup rice",
        },
    )

    assert response.status_code == 201
    assert captured["caption_text"] == "1 cup rice"
    assert response.json()["title"] == "Manual Recipe"


def test_ingest_recipe_maps_known_errors_to_422(client, monkeypatch):
    from app.parsing.recipe_parser import RecipeParseError

    def fake_ingest_youtube(db, user_id, url):
        raise RecipeParseError("model declined")

    monkeypatch.setattr("app.api.routes.ingest_youtube", fake_ingest_youtube)

    response = client.post(
        "/recipes/ingest",
        json={"source_platform": "youtube", "url": "https://youtube.com/watch?v=abc"},
    )

    assert response.status_code == 422
    assert "model declined" in response.json()["detail"]


def test_list_recipes_scoped_to_current_user(client, db_session):
    user_id = get_current_user_id(db_session)
    _make_recipe(db_session, user_id, title="Recipe A")
    _make_recipe(db_session, user_id, title="Recipe B")

    response = client.get("/recipes")

    assert response.status_code == 200
    titles = {r["title"] for r in response.json()}
    assert titles == {"Recipe A", "Recipe B"}


def test_list_recipes_filters_by_cuisine(client, db_session):
    user_id = get_current_user_id(db_session)
    _make_recipe(db_session, user_id, title="Bibimbap", cuisine="korean")
    _make_recipe(db_session, user_id, title="Tacos", cuisine="mexican")

    response = client.get("/recipes", params={"cuisine": "korean"})

    assert response.status_code == 200
    titles = [r["title"] for r in response.json()]
    assert titles == ["Bibimbap"]


def test_list_recipes_filters_by_meal_type(client, db_session):
    user_id = get_current_user_id(db_session)
    _make_recipe(db_session, user_id, title="Pancakes", meal_type="breakfast")
    _make_recipe(db_session, user_id, title="Steak", meal_type="dinner")

    response = client.get("/recipes", params={"meal_type": "breakfast"})

    assert response.status_code == 200
    titles = [r["title"] for r in response.json()]
    assert titles == ["Pancakes"]


def test_list_recipes_filters_by_max_cook_time_and_excludes_unknown(client, db_session):
    user_id = get_current_user_id(db_session)
    _make_recipe(db_session, user_id, title="Quick Stir Fry", cook_time_minutes=15)
    _make_recipe(db_session, user_id, title="Slow Roast", cook_time_minutes=180)
    _make_recipe(db_session, user_id, title="Unknown Time", cook_time_minutes=None)

    response = client.get("/recipes", params={"max_cook_time_minutes": 30})

    assert response.status_code == 200
    titles = [r["title"] for r in response.json()]
    assert titles == ["Quick Stir Fry"]


def test_update_recipe_updates_fields_and_ingredients(client, db_session):
    user_id = get_current_user_id(db_session)
    recipe = _make_recipe(db_session, user_id, title="Fried Rice", ingredients=["rice"])

    response = client.put(
        f"/recipes/{recipe.id}",
        json={
            "title": "Better Fried Rice",
            "steps": ["Step one", "Step two"],
            "cuisine": "chinese",
            "meal_type": "dinner",
            "cook_time_minutes": 20,
            "ingredients": [{"name": "rice", "quantity": "2 cups"}, {"name": "eggs"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Better Fried Rice"
    assert body["steps"] == ["Step one", "Step two"]
    assert body["cuisine"] == "chinese"
    assert body["meal_type"] == "dinner"
    assert body["cook_time_minutes"] == 20
    names = {i["name"] for i in body["ingredients"]}
    assert names == {"rice", "eggs"}


def test_update_recipe_rejects_cuisine_outside_allowed_set(client, db_session):
    user_id = get_current_user_id(db_session)
    recipe = _make_recipe(db_session, user_id)

    response = client.put(
        f"/recipes/{recipe.id}",
        json={
            "title": "X",
            "steps": [],
            "cuisine": "klingon",
            "ingredients": [],
        },
    )

    assert response.status_code == 422


def test_update_recipe_returns_404_for_nonexistent_recipe(client, db_session):
    get_current_user_id(db_session)

    response = client.put(
        "/recipes/999999",
        json={"title": "X", "steps": [], "ingredients": []},
    )

    assert response.status_code == 404


def test_update_recipe_returns_404_for_another_users_recipe(client, db_session):
    from app.models import User

    other_user = User(email="someone-else@example.com")
    db_session.add(other_user)
    db_session.flush()
    other_recipe = _make_recipe(db_session, other_user.id, title="Not Yours")

    get_current_user_id(db_session)  # ensures the default user exists too

    response = client.put(
        f"/recipes/{other_recipe.id}",
        json={"title": "Hijacked", "steps": [], "ingredients": []},
    )

    assert response.status_code == 404


def test_match_pantry_returns_ranked_matches(client, db_session):
    user_id = get_current_user_id(db_session)
    _make_recipe(db_session, user_id, title="Full Match", ingredients=["rice"])
    _make_recipe(db_session, user_id, title="No Match", ingredients=["durian"])

    response = client.post("/match", json={"pantry": ["rice"]})

    assert response.status_code == 200
    results = response.json()
    assert results[0]["recipe"]["title"] == "Full Match"
    assert results[0]["match_ratio"] == 1.0
    assert results[1]["recipe"]["title"] == "No Match"
    assert results[1]["match_ratio"] == 0.0
