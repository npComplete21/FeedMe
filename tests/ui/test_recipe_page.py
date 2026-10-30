"""The recipe page: read, rate, edit.

Driven through the real entry file (AppTest + a stub API client), switched to
the recipe page the way the app does it: an id in `?recipe=` and/or in session
state. AppTest sees elements and session state but not CSS or a real browser
refresh, so layout and the refresh case are checked live instead.
"""

import httpx
from streamlit.testing.v1 import AppTest

from app.ui import api

ENTRY = "app/ui/streamlit_app.py"
PAGE = "views/recipe.py"


def _recipe(id, title, **extra):
    return {
        "id": id,
        "title": title,
        "source_url": f"https://example.com/{id}",
        "source_platform": "website",
        "cuisine": "italian",
        "meal_type": "dinner",
        "cook_time_minutes": 30,
        "rating": 4,
        "steps": ["Boil the pasta", "Fry the guanciale"],
        "ingredients": [
            {"name": "spaghetti", "quantity": "200 g"},
            {"name": "egg", "quantity": None},
        ],
        "created_at": "2026-10-01T00:00:00",
        **extra,
    }


RECIPES = [
    _recipe(1, "Margherita pizza", rating=None, cuisine=None, meal_type=None, cook_time_minutes=None),
    _recipe(2, "Carbonara"),
]


class _StubClient:
    """GET /recipes returns the list; PUTs are applied to it and recorded."""

    def __init__(self, recipes):
        self.recipes = [dict(r) for r in recipes]
        self.puts = []
        self.get_count = 0

    def get(self, url, params=None, **kwargs):
        assert url == "/recipes"
        self.get_count += 1
        return httpx.Response(200, json=self.recipes, request=httpx.Request("GET", "http://stub"))

    def put(self, url, json=None, **kwargs):
        self.puts.append((url, json))
        status = 200
        parts = url.split("/")  # "", "recipes", "<id>"[, "rating"]
        target = next(r for r in self.recipes if r["id"] == int(parts[2]))
        if len(parts) == 4:
            target["rating"] = json["rating"]
        else:
            target.update(json)
        return httpx.Response(status, json=target, request=httpx.Request("PUT", "http://stub"))


def _open(monkeypatch, recipe_param=None, session_id=None, recipes=RECIPES):
    client = _StubClient(recipes)
    monkeypatch.setattr(api, "get_client", lambda: client)
    at = AppTest.from_file(ENTRY)
    at.session_state["access_token"] = "t"
    at.session_state["user_email"] = "cook@example.com"
    if session_id is not None:
        at.session_state["open_recipe_id"] = session_id
    if recipe_param is not None:
        at.query_params["recipe"] = recipe_param
    at.switch_page(PAGE)
    at.run()
    assert not at.exception
    return at, client


def _text(at: AppTest) -> str:
    return "\n".join(
        el.value for el in [*at.markdown, *at.info, *at.caption, *at.subheader, *at.header, *at.error]
    )


def _links(at: AppTest) -> list:
    return [link.proto for link in at.get("page_link")]


def test_renders_ingredients_and_steps_for_id_from_session(monkeypatch):
    at, _ = _open(monkeypatch, session_id=2)

    text = _text(at)
    assert "Carbonara" in text
    assert "200 g spaghetti" in text
    assert "egg" in text
    assert "1. Boil the pasta" in text
    assert "2. Fry the guanciale" in text
    # The id is written back to the URL so a refresh reopens this recipe.
    assert at.query_params["recipe"] == ["2"]


def test_shows_tags_and_source_link(monkeypatch):
    at, _ = _open(monkeypatch, session_id=2)

    text = _text(at)
    assert "Italian · Dinner · 30 min · ★★★★" in text
    assert "https://example.com/2" in str(at.get("link_button")[0].proto.url)


def test_id_from_query_param_wins(monkeypatch):
    at, _ = _open(monkeypatch, recipe_param="1", session_id=2)

    assert "Margherita pizza" in _text(at)
    assert "Carbonara" not in _text(at)


def test_query_param_alone_is_enough_after_a_refresh(monkeypatch):
    # A browser refresh keeps ?recipe= but loses session state.
    at, _ = _open(monkeypatch, recipe_param="2")

    assert "Carbonara" in _text(at)


def test_unknown_id_shows_not_found_with_back_link(monkeypatch):
    at, _ = _open(monkeypatch, recipe_param="99999")

    assert "Recipe not found" in _text(at)
    assert any("Back to recipes" in link.label for link in _links(at))


def test_non_numeric_id_shows_not_found(monkeypatch):
    at, _ = _open(monkeypatch, recipe_param="abc", session_id=2)

    assert "Recipe not found" in _text(at)
    # Garbage in the URL does not silently fall back to the session's recipe.
    assert "Carbonara" not in _text(at)


def test_no_id_at_all_shows_not_found(monkeypatch):
    at, _ = _open(monkeypatch)

    assert "Recipe not found" in _text(at)


def test_back_link_points_at_recipes(monkeypatch):
    at, _ = _open(monkeypatch, recipe_param="2")

    back = [link for link in _links(at) if "Back to recipes" in link.label]
    assert len(back) == 1
    # Same target as the Recipes tab in the bottom bar.
    tab = next(link for link in _links(at) if link.label == "Recipes")
    assert back[0].page_script_hash == tab.page_script_hash


def test_title_is_markdown_escaped(monkeypatch):
    recipes = [_recipe(5, "Mac *n* $5")]
    at, _ = _open(monkeypatch, recipe_param="5", recipes=recipes)

    assert "Mac \\*n\\* \\$5" in _text(at)


def test_rating_widget_starts_at_saved_rating(monkeypatch):
    at, _ = _open(monkeypatch, recipe_param="2")

    # st.feedback("stars") is 0-4; the saved rating is 1-5.
    assert at.feedback(key="rating-2").value == 3


def test_rating_sends_one_to_five(monkeypatch):
    at, client = _open(monkeypatch, recipe_param="1")

    at.feedback(key="rating-1").set_value(4).run()

    assert not at.exception
    assert client.puts == [("/recipes/1/rating", {"rating": 5})]
    assert "★★★★★" in _text(at)


def test_clearing_rating_sends_null(monkeypatch):
    at, client = _open(monkeypatch, recipe_param="2")

    at.feedback(key="rating-2").set_value(None).run()

    assert not at.exception
    assert client.puts == [("/recipes/2/rating", {"rating": None})]


def test_edit_form_hidden_until_edit_pressed(monkeypatch):
    at, _ = _open(monkeypatch, recipe_param="2")

    assert len(at.text_input) == 0
    assert len(at.text_area) == 0
    at.button(key="edit-2").click().run()

    assert not at.exception
    assert at.text_input[0].value == "Carbonara"
    assert len(at.text_area) == 2


def test_edit_form_prefills_the_recipe(monkeypatch):
    at, _ = _open(monkeypatch, recipe_param="2")
    at.button(key="edit-2").click().run()

    assert at.text_area[0].value == "Boil the pasta\nFry the guanciale"
    assert at.text_area[1].value == "spaghetti, 200 g\negg"
    assert at.selectbox[0].value == "italian"
    assert at.selectbox[1].value == "dinner"
    assert at.number_input[0].value == 30


def test_edit_mode_is_per_recipe(monkeypatch):
    at, _ = _open(monkeypatch, recipe_param="2")
    at.button(key="edit-2").click().run()

    at.query_params["recipe"] = "1"
    at.run()

    assert not at.exception
    assert "Margherita pizza" in _text(at)
    assert len(at.text_input) == 0
    assert at.button(key="edit-1") is not None


def test_save_sends_put_with_parsed_ingredients(monkeypatch):
    at, client = _open(monkeypatch, recipe_param="1")
    at.button(key="edit-1").click().run()

    at.text_input[0].set_value("Margherita deluxe")
    at.text_area[0].set_value("Knead\n\nBake  ")
    at.text_area[1].set_value("flour, 500 g\nbasil\n\n")
    at.number_input[0].set_value(0)
    at.button(key="edit-save-1").click().run()

    assert not at.exception
    assert client.puts == [
        (
            "/recipes/1",
            {
                "title": "Margherita deluxe",
                "steps": ["Knead", "Bake"],
                "cuisine": None,  # "(none)"
                "meal_type": None,
                "cook_time_minutes": None,  # 0 = unknown
                "ingredients": [
                    {"name": "flour", "quantity": "500 g"},
                    {"name": "basil", "quantity": None},
                ],
            },
        )
    ]


def test_save_returns_to_read_mode_with_new_values(monkeypatch):
    at, _ = _open(monkeypatch, recipe_param="1")
    at.button(key="edit-1").click().run()
    at.text_input[0].set_value("Margherita deluxe")
    at.selectbox[0].select("thai")

    at.button(key="edit-save-1").click().run()

    assert not at.exception
    assert len(at.text_input) == 0
    assert "Margherita deluxe" in _text(at)
    assert "Thai" in _text(at)


def test_cancel_returns_to_read_mode_without_a_put(monkeypatch):
    at, client = _open(monkeypatch, recipe_param="2")
    at.button(key="edit-2").click().run()
    at.text_input[0].set_value("Changed my mind")

    at.button(key="edit-cancel-2").click().run()

    assert not at.exception
    assert client.puts == []
    assert len(at.text_input) == 0
    assert "Carbonara" in _text(at)
    assert "Changed my mind" not in _text(at)


def test_failed_save_keeps_the_form_and_shows_the_error(monkeypatch):
    at, client = _open(monkeypatch, recipe_param="2")

    def failing_put(url, json=None, **kwargs):
        response = httpx.Response(
            422, json={"detail": "bad cuisine"}, request=httpx.Request("PUT", "http://stub")
        )
        raise httpx.HTTPStatusError("422", request=response.request, response=response)

    client.put = failing_put
    at.button(key="edit-2").click().run()
    at.button(key="edit-save-2").click().run()

    assert not at.exception
    assert len(at.text_input) == 1
    assert "bad cuisine" in "\n".join(e.value for e in at.error)
