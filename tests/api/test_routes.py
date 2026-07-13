from app.api.deps import get_current_user_id
from app.models import Ingredient, Recipe, RecipeIngredient


def _make_recipe(db_session, user_id, title="Fried Rice", ingredients=None):
    recipe = Recipe(
        user_id=user_id,
        source_url="https://youtube.com/watch?v=abc",
        source_platform="youtube",
        title=title,
        steps=["step"],
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
