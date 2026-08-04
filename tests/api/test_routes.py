from unittest.mock import MagicMock

from app.api.converters import recipe_to_response
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


def test_ingest_recipe_youtube_enqueues_task(client, monkeypatch, db_session, test_user_id):
    fake_task = MagicMock()
    fake_task.delay.return_value.id = "task-abc"
    monkeypatch.setattr("app.api.routes.ingest_youtube_task", fake_task)

    response = client.post(
        "/recipes/ingest",
        json={"source_platform": "youtube", "url": "https://youtube.com/watch?v=abc"},
    )

    assert response.status_code == 202
    assert response.json() == {"task_id": "task-abc"}
    fake_task.delay.assert_called_once_with(test_user_id, "https://youtube.com/watch?v=abc")


def test_ingest_recipe_manual_requires_caption_text(client):
    response = client.post(
        "/recipes/ingest",
        json={"source_platform": "instagram", "url": "https://instagram.com/reel/abc"},
    )

    assert response.status_code == 422


def test_ingest_recipe_manual_enqueues_task_with_caption(
    client, monkeypatch, db_session, test_user_id
):
    fake_task = MagicMock()
    fake_task.delay.return_value.id = "task-xyz"
    monkeypatch.setattr("app.api.routes.ingest_manual_caption_task", fake_task)

    response = client.post(
        "/recipes/ingest",
        json={
            "source_platform": "instagram",
            "url": "https://instagram.com/reel/abc",
            "caption_text": "1 cup rice",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"task_id": "task-xyz"}
    fake_task.delay.assert_called_once_with(
        test_user_id, "https://instagram.com/reel/abc", "1 cup rice", "instagram"
    )


def test_ingest_status_pending(client, monkeypatch):
    fake_result = MagicMock()
    fake_result.successful.return_value = False
    fake_result.failed.return_value = False
    monkeypatch.setattr("app.api.routes.AsyncResult", lambda task_id, app: fake_result)

    response = client.get("/recipes/ingest/some-task-id")

    assert response.status_code == 200
    assert response.json() == {"state": "pending", "recipe": None, "error": None}


def test_ingest_status_success_returns_recipe(client, monkeypatch, db_session, test_user_id):
    recipe = _make_recipe(db_session, test_user_id, title="Fried Rice", ingredients=["rice"])

    fake_result = MagicMock()
    fake_result.successful.return_value = True
    fake_result.failed.return_value = False
    fake_result.result = recipe_to_response(recipe).model_dump(mode="json")
    monkeypatch.setattr("app.api.routes.AsyncResult", lambda task_id, app: fake_result)

    response = client.get("/recipes/ingest/some-task-id")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "success"
    assert body["recipe"]["title"] == "Fried Rice"
    assert body["error"] is None


def test_ingest_status_failure_returns_error(client, monkeypatch):
    fake_result = MagicMock()
    fake_result.successful.return_value = False
    fake_result.failed.return_value = True
    fake_result.result = ValueError("No captions available for this video")
    monkeypatch.setattr("app.api.routes.AsyncResult", lambda task_id, app: fake_result)

    response = client.get("/recipes/ingest/some-task-id")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "failure"
    assert "No captions available" in body["error"]
    assert body["recipe"] is None


def test_list_recipes_scoped_to_current_user(client, db_session, test_user_id):
    _make_recipe(db_session, test_user_id, title="Recipe A")
    _make_recipe(db_session, test_user_id, title="Recipe B")

    response = client.get("/recipes")

    assert response.status_code == 200
    titles = {r["title"] for r in response.json()}
    assert titles == {"Recipe A", "Recipe B"}


def test_list_recipes_filters_by_cuisine(client, db_session, test_user_id):
    _make_recipe(db_session, test_user_id, title="Bibimbap", cuisine="korean")
    _make_recipe(db_session, test_user_id, title="Tacos", cuisine="mexican")

    response = client.get("/recipes", params={"cuisine": "korean"})

    assert response.status_code == 200
    titles = [r["title"] for r in response.json()]
    assert titles == ["Bibimbap"]


def test_list_recipes_filters_by_meal_type(client, db_session, test_user_id):
    _make_recipe(db_session, test_user_id, title="Pancakes", meal_type="breakfast")
    _make_recipe(db_session, test_user_id, title="Steak", meal_type="dinner")

    response = client.get("/recipes", params={"meal_type": "breakfast"})

    assert response.status_code == 200
    titles = [r["title"] for r in response.json()]
    assert titles == ["Pancakes"]


def test_list_recipes_filters_by_max_cook_time_and_excludes_unknown(
    client, db_session, test_user_id
):
    _make_recipe(db_session, test_user_id, title="Quick Stir Fry", cook_time_minutes=15)
    _make_recipe(db_session, test_user_id, title="Slow Roast", cook_time_minutes=180)
    _make_recipe(db_session, test_user_id, title="Unknown Time", cook_time_minutes=None)

    response = client.get("/recipes", params={"max_cook_time_minutes": 30})

    assert response.status_code == 200
    titles = [r["title"] for r in response.json()]
    assert titles == ["Quick Stir Fry"]


def test_update_recipe_updates_fields_and_ingredients(client, db_session, test_user_id):
    recipe = _make_recipe(db_session, test_user_id, title="Fried Rice", ingredients=["rice"])

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


def test_update_recipe_rejects_cuisine_outside_allowed_set(client, db_session, test_user_id):
    recipe = _make_recipe(db_session, test_user_id)

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
    response = client.put(
        "/recipes/999999",
        json={"title": "X", "steps": [], "ingredients": []},
    )

    assert response.status_code == 404


def test_update_recipe_returns_404_for_another_users_recipe(client, db_session):
    from tests.conftest import create_test_user

    other_user_id = create_test_user(db_session, email="someone-else@example.com")
    other_recipe = _make_recipe(db_session, other_user_id, title="Not Yours")

    response = client.put(
        f"/recipes/{other_recipe.id}",
        json={"title": "Hijacked", "steps": [], "ingredients": []},
    )

    assert response.status_code == 404


def test_match_pantry_returns_ranked_matches(client, db_session, test_user_id):
    _make_recipe(db_session, test_user_id, title="Full Match", ingredients=["rice"])
    _make_recipe(db_session, test_user_id, title="No Match", ingredients=["durian"])

    response = client.post("/match", json={"pantry": ["rice"]})

    assert response.status_code == 200
    results = response.json()
    assert results[0]["recipe"]["title"] == "Full Match"
    assert results[0]["match_ratio"] == 1.0
    assert results[1]["recipe"]["title"] == "No Match"
    assert results[1]["match_ratio"] == 0.0


def test_chat_returns_reply_and_history(client, db_session, monkeypatch):
    from app.chat.recipe_chat import ChatReply

    captured = {}

    def fake_chat_about_recipes(db, user_id, message, history=None, **kwargs):
        captured["message"] = message
        captured["history"] = history
        return ChatReply(
            reply="Try Fried Rice.",
            messages=[*(history or []), {"role": "user", "content": message}],
        )

    monkeypatch.setattr("app.api.routes.chat_about_recipes", fake_chat_about_recipes)

    response = client.post("/chat", json={"message": "I have rice, what can I make?"})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Try Fried Rice."
    assert body["history"][-1] == {"role": "user", "content": "I have rice, what can I make?"}
    assert captured["message"] == "I have rice, what can I make?"
    assert captured["history"] == []


def test_chat_passes_through_history(client, db_session, monkeypatch):
    from app.chat.recipe_chat import ChatReply

    captured = {}

    def fake_chat_about_recipes(db, user_id, message, history=None, **kwargs):
        captured["history"] = history
        return ChatReply(reply="ok", messages=[])

    monkeypatch.setattr("app.api.routes.chat_about_recipes", fake_chat_about_recipes)

    prior_history = [{"role": "user", "content": "hi"}]
    response = client.post("/chat", json={"message": "again", "history": prior_history})

    assert response.status_code == 200
    assert captured["history"] == prior_history


def test_chat_maps_refusal_to_422(client, db_session, monkeypatch):
    from app.chat.recipe_chat import RecipeChatError

    def fake_chat_about_recipes(db, user_id, message, history=None, **kwargs):
        raise RecipeChatError("Model declined to respond")

    monkeypatch.setattr("app.api.routes.chat_about_recipes", fake_chat_about_recipes)

    response = client.post("/chat", json={"message": "anything"})

    assert response.status_code == 422
    assert "declined" in response.json()["detail"]
