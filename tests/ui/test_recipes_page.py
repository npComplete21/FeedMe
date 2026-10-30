"""The Recipes tab: search, cuisine boxes, recipe lists.

Driven through the real entry file with Streamlit's AppTest and a stub API
client, so the hidden navigation, login gate and the page all run for real.
AppTest sees elements and session state but not CSS (the 2-up grid, the row
look, the tab bar not covering the last row), which are checked live instead.
"""

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from app.ui import api, nav

ENTRY = "app/ui/streamlit_app.py"


def _recipe(id, title, cuisine, rating, ingredients, **extra):
    return {
        "id": id,
        "title": title,
        "cuisine": cuisine,
        "rating": rating,
        "meal_type": None,
        "cook_time_minutes": None,
        "steps": [],
        "ingredients": [{"name": name, "quantity": None} for name in ingredients],
        **extra,
    }


RECIPES = [
    _recipe(1, "Margherita pizza", "italian", 5, ["basil", "mozzarella"], cook_time_minutes=30),
    _recipe(2, "Carbonara", "italian", 3, ["guanciale", "egg"]),
    _recipe(3, "Kimchi fried rice", "korean", None, ["kimchi", "rice"]),
    _recipe(4, "Buttered toast", None, None, ["bread", "butter"]),
]


class _StubClient:
    """Answers GET /recipes with a fixed list and remembers the params it saw."""

    def __init__(self, recipes):
        self.recipes = recipes
        self.calls = []

    def get(self, url, params=None, **kwargs):
        assert url == "/recipes"
        self.calls.append(dict(params or {}))
        return httpx.Response(200, json=self.recipes, request=httpx.Request("GET", "http://stub"))


def _open(monkeypatch, recipes=RECIPES) -> tuple[AppTest, _StubClient]:
    client = _StubClient(recipes)
    monkeypatch.setattr(api, "get_client", lambda: client)
    at = AppTest.from_file(ENTRY)
    at.session_state["access_token"] = "t"
    at.session_state["user_email"] = "cook@example.com"
    at.run()
    assert not at.exception
    return at, client


def _keys(at: AppTest, prefix: str) -> list[str]:
    return [b.key for b in at.button if b.key and b.key.startswith(prefix)]


def _text(at: AppTest) -> str:
    return "\n".join(el.value for el in [*at.markdown, *at.info, *at.caption])


def _search(at: AppTest, query: str) -> AppTest:
    at.text_input(key="recipes_query_widget").input(query).run()
    assert not at.exception
    return at


def test_boxes_show_counts_and_all_box(monkeypatch):
    at, _ = _open(monkeypatch)

    assert _keys(at, "cuisine-box-") == [
        "cuisine-box-italian",
        "cuisine-box-korean",
        "cuisine-box-all",
    ]
    italian = at.button(key="cuisine-box-italian").label
    assert "Italian" in italian and "2 recipes" in italian
    korean = at.button(key="cuisine-box-korean").label
    assert "Korean" in korean and "1 recipe" in korean and "1 recipes" not in korean
    assert "All recipes · 4" in at.button(key="cuisine-box-all").label
    # Boxes, not rows: no recipe list until a box is tapped.
    assert _keys(at, "recipe-row-") == []


def test_uncategorised_recipe_reachable_via_all(monkeypatch):
    at, _ = _open(monkeypatch)

    at.button(key="cuisine-box-all").click().run()

    assert not at.exception
    assert _keys(at, "recipe-row-") == [f"recipe-row-list-{i}" for i in (1, 2, 3, 4)]
    assert _keys(at, "cuisine-box-") == []


def test_cuisine_box_lists_only_that_cuisine_in_api_order(monkeypatch):
    at, _ = _open(monkeypatch)

    at.button(key="cuisine-box-italian").click().run()

    assert _keys(at, "recipe-row-") == ["recipe-row-list-1", "recipe-row-list-2"]
    assert [h.value for h in at.subheader] == ["🍝 Italian"]


def test_back_returns_to_boxes(monkeypatch):
    at, _ = _open(monkeypatch)
    at.button(key="cuisine-box-italian").click().run()

    at.button(key="recipes-back").click().run()

    assert not at.exception
    assert _keys(at, "recipe-row-") == []
    assert "cuisine-box-italian" in _keys(at, "cuisine-box-")


def test_search_replaces_boxes_and_filters(monkeypatch):
    at, _ = _open(monkeypatch)

    _search(at, "KIMCHI")

    assert _keys(at, "cuisine-box-") == []
    assert _keys(at, "recipe-row-") == ["recipe-row-search-3"]


def test_search_matches_ingredients(monkeypatch):
    at, _ = _open(monkeypatch)

    _search(at, "mozzarella")

    assert _keys(at, "recipe-row-") == ["recipe-row-search-1"]


def test_whitespace_search_is_ignored(monkeypatch):
    at, _ = _open(monkeypatch)

    _search(at, "   ")

    assert "cuisine-box-all" in _keys(at, "cuisine-box-")
    assert _keys(at, "recipe-row-") == []


def test_clearing_search_returns_to_boxes(monkeypatch):
    at, _ = _open(monkeypatch)
    _search(at, "kimchi")

    _search(at, "")

    assert "cuisine-box-all" in _keys(at, "cuisine-box-")
    assert _keys(at, "recipe-row-") == []


def test_search_no_match_shows_empty_state(monkeypatch):
    at, _ = _open(monkeypatch)

    _search(at, "sushi")

    assert "No recipes match “sushi”" in _text(at)
    assert _keys(at, "recipe-row-") == []
    assert _keys(at, "cuisine-box-") == []


def test_no_match_message_escapes_the_query(monkeypatch):
    at, _ = _open(monkeypatch)

    _search(at, "*zz* [q]")

    assert r"No recipes match “\*zz\* \[q\]”" in _text(at)


def test_empty_library_message(monkeypatch):
    at, _ = _open(monkeypatch, recipes=[])

    assert "No recipes yet — tap ＋ to save your first one" in _text(at)
    assert _keys(at, "cuisine-box-") == []


def test_default_sort_param_is_rating(monkeypatch):
    _, client = _open(monkeypatch)

    assert client.calls == [{"sort": "rating"}]


def test_sort_switch_to_newest_refetches_and_survives_navigation(monkeypatch):
    at, client = _open(monkeypatch)
    at.button(key="cuisine-box-all").click().run()

    at.selectbox(key="recipes_sort_widget").select("newest").run()

    assert not at.exception
    assert client.calls[-1] == {"sort": "newest"}
    # Back to the boxes and into a list again: the choice is remembered.
    at.button(key="recipes-back").click().run()
    assert client.calls[-1] == {"sort": "newest"}
    at.button(key="cuisine-box-italian").click().run()
    assert at.selectbox(key="recipes_sort_widget").value == "newest"


def test_search_results_use_the_sort_control(monkeypatch):
    at, client = _open(monkeypatch)
    _search(at, "rice")

    at.selectbox(key="recipes_sort_widget").select("newest").run()

    assert client.calls[-1] == {"sort": "newest"}
    assert _keys(at, "recipe-row-") == ["recipe-row-search-3"]


def test_cuisine_is_not_sent_to_the_api(monkeypatch):
    at, client = _open(monkeypatch)
    at.button(key="cuisine-box-korean").click().run()

    assert all("cuisine" not in call for call in client.calls)


def test_tapping_a_row_opens_the_recipe(monkeypatch):
    opened = []
    monkeypatch.setattr(nav, "open_recipe", opened.append)
    at, _ = _open(monkeypatch)
    at.button(key="cuisine-box-korean").click().run()

    at.button(key="recipe-row-list-3").click().run()

    assert opened == [3]


def test_row_shows_title_and_tag_line(monkeypatch):
    at, _ = _open(monkeypatch)
    at.button(key="cuisine-box-italian").click().run()

    label = at.button(key="recipe-row-list-1").label
    assert "Margherita pizza" in label
    assert "Italian · 30 min · ★★★★★" in label


def test_row_title_is_escaped_for_markdown(monkeypatch):
    recipes = [_recipe(9, "Mac *n* cheese $5 _deal_", "american", None, ["pasta"])]
    at, _ = _open(monkeypatch, recipes=recipes)
    at.button(key="cuisine-box-all").click().run()

    label = at.button(key="recipe-row-list-9").label
    assert "Mac \\*n\\* cheese \\$5 \\_deal\\_" in label


def test_stale_cuisine_selection_falls_back_to_boxes(monkeypatch):
    # The selected cuisine's last recipe was deleted/re-tagged elsewhere.
    at, client = _open(monkeypatch)
    at.button(key="cuisine-box-korean").click().run()
    client.recipes = [r for r in RECIPES if r["cuisine"] != "korean"]

    at.run()

    assert not at.exception
    assert "cuisine-box-all" in _keys(at, "cuisine-box-")


@pytest.mark.parametrize("failure", [httpx.ConnectError("down")])
def test_api_error_shows_message_not_traceback(monkeypatch, failure):
    class _Failing:
        def get(self, *args, **kwargs):
            raise failure

    monkeypatch.setattr(api, "get_client", lambda: _Failing())
    at = AppTest.from_file(ENTRY)
    at.session_state["access_token"] = "t"
    at.session_state["user_email"] = "cook@example.com"
    at.run()

    assert not at.exception
    assert any("Couldn't load recipes" in e.value for e in at.error)
