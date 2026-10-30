"""The Pantry tab: type what you have, find recipes, see Have / Missing.

Driven through the real entry file with AppTest and a stub API client that
records every POST /match. AppTest sees elements and session state but not CSS or
the tab bar, so phone layout is checked live instead.
"""

import httpx
from streamlit.testing.v1 import AppTest

from app.ui import api

ENTRY = "app/ui/streamlit_app.py"
PAGE = "views/pantry.py"
OTHER_PAGE = "views/save.py"


def _match(id, title, ratio, have, missing):
    return {
        "recipe": {
            "id": id,
            "title": title,
            "source_url": "https://example.com/r",
            "steps": ["Do not show me inline"],
            "ingredients": [],
        },
        "match_ratio": ratio,
        "matched_ingredients": have,
        "missing_ingredients": missing,
    }


MATCHES = [
    _match(1, "Carbonara", 0.5, ["egg", "pasta"], ["guanciale", "pecorino"]),
    _match(2, "Plain pasta", 1.0, ["pasta"], []),
]


class _StubClient:
    """POST /match answers with `matches` (or a failure); records each payload."""

    def __init__(self, matches=MATCHES, post_status=200, error=None):
        self.matches = matches
        self.post_status = post_status
        self.error = error
        self.posts = []

    def post(self, url, json=None, **kwargs):
        assert url == "/match"
        self.posts.append(json)
        if self.error:
            raise self.error
        request = httpx.Request("POST", "http://stub")
        if self.post_status >= 400:
            return httpx.Response(self.post_status, json={"detail": "nope"}, request=request)
        return httpx.Response(200, json=self.matches, request=request)

    def get(self, url, **kwargs):  # the recipe page, once "Open recipe" is tapped
        return httpx.Response(200, json=[], request=httpx.Request("GET", "http://stub"))


def _open(monkeypatch, client=None, **session):
    client = client or _StubClient()
    monkeypatch.setattr(api, "get_client", lambda: client)
    at = AppTest.from_file(ENTRY, default_timeout=10)
    at.session_state["access_token"] = "t"
    at.session_state["user_email"] = "cook@example.com"
    for key, value in session.items():
        at.session_state[key] = value
    at.switch_page(PAGE)
    at.run()
    assert not at.exception
    return at, client


def _find(at, text):
    at.text_input(key="pantry_text_widget").set_value(text).run()
    at.button(key="pantry-find").click().run()
    assert not at.exception


def _text(at):
    return "\n".join(el.value for el in [*at.markdown, *at.info, *at.error, *at.caption, *at.warning])


def _keys(at, prefix):
    return [b.key for b in at.button if b.key and b.key.startswith(prefix)]


def test_blank_pantry_makes_no_request(monkeypatch):
    at, client = _open(monkeypatch)

    _find(at, "")

    assert client.posts == []
    assert "Type what you have" in _text(at)


def test_only_commas_and_spaces_makes_no_request(monkeypatch):
    at, client = _open(monkeypatch)

    _find(at, " , ,, ")

    assert client.posts == []
    assert "Type what you have" in _text(at)


def test_pantry_payload_is_parsed_list(monkeypatch):
    at, client = _open(monkeypatch)

    _find(at, " egg, pasta ,, Parmesan ")

    assert client.posts == [{"pantry": ["egg", "pasta", "Parmesan"]}]


def test_results_show_have_and_missing(monkeypatch):
    at, _ = _open(monkeypatch)

    _find(at, "egg, pasta")

    text = _text(at)
    assert "Carbonara" in text and "50% match" in text
    assert "Plain pasta" in text and "100% match" in text
    assert "**Have:** egg, pasta" in text
    assert "**Missing:** guanciale, pecorino" in text
    assert "**Missing:** none" in text
    # No inline source or steps: they live on the recipe page.
    assert "Do not show me inline" not in text
    assert "Source" not in text
    assert _keys(at, "pantry-open-") == ["pantry-open-1", "pantry-open-2"]


def test_no_matches_message(monkeypatch):
    at, _ = _open(monkeypatch, _StubClient(matches=[]))

    _find(at, "dust")

    assert "No matches." in _text(at)
    assert _keys(at, "pantry-open-") == []


def test_open_recipe_button_goes_to_the_recipe_page(monkeypatch):
    at, _ = _open(monkeypatch)
    _find(at, "egg")

    at.button(key="pantry-open-2").click().run()

    assert not at.exception
    assert at.session_state["open_recipe_id"] == 2
    assert at.query_params["recipe"] == ["2"]


def test_pantry_text_persists_in_session_state(monkeypatch):
    at, _ = _open(monkeypatch)
    _find(at, "egg, pasta")

    assert at.session_state["pantry_text"] == "egg, pasta"

    at.switch_page(OTHER_PAGE).run()
    assert not at.exception
    at.switch_page(PAGE).run()
    assert not at.exception

    assert at.text_input(key="pantry_text_widget").value == "egg, pasta"


def test_results_survive_switching_tabs_without_a_new_request(monkeypatch):
    at, client = _open(monkeypatch)
    _find(at, "egg, pasta")

    at.switch_page(OTHER_PAGE).run()
    at.switch_page(PAGE).run()

    assert not at.exception
    assert len(client.posts) == 1
    assert "Carbonara" in _text(at)
    assert _keys(at, "pantry-open-") == ["pantry-open-1", "pantry-open-2"]


def test_no_matches_survives_switching_tabs(monkeypatch):
    at, _ = _open(monkeypatch, _StubClient(matches=[]))
    _find(at, "dust")

    at.switch_page(OTHER_PAGE).run()
    at.switch_page(PAGE).run()

    assert "No matches." in _text(at)


def test_fresh_session_shows_no_results_or_messages(monkeypatch):
    at, client = _open(monkeypatch)

    assert client.posts == []
    assert _keys(at, "pantry-open-") == []
    assert "No matches." not in _text(at)
    assert not at.error


def test_api_error_is_inline_and_keeps_previous_results(monkeypatch):
    client = _StubClient()
    at, _ = _open(monkeypatch, client)
    _find(at, "egg")
    client.post_status = 500

    _find(at, "pasta")

    assert [e.value for e in at.error] == ["nope"]
    assert "Carbonara" in _text(at)


def test_network_error_is_inline(monkeypatch):
    at, _ = _open(monkeypatch, _StubClient(error=httpx.ConnectError("boom")))

    _find(at, "egg")

    assert [e.value for e in at.error] == ["Request failed: boom"]
    assert "No matches." not in _text(at)


def test_error_text_is_escaped(monkeypatch):
    at, _ = _open(monkeypatch, _StubClient(error=httpx.ConnectError("*bad* [x]")))

    _find(at, "egg")

    assert [e.value for e in at.error] == [r"Request failed: \*bad\* \[x\]"]


def test_titles_and_ingredients_are_escaped(monkeypatch):
    matches = [_match(1, "*Spicy* [mix]", 0.5, ["_salt_"], ["`oil`"])]
    at, _ = _open(monkeypatch, _StubClient(matches=matches))

    _find(at, "salt")

    text = _text(at)
    assert r"\*Spicy\* \[mix\]" in text
    assert r"\_salt\_" in text
    assert r"\`oil\`" in text
