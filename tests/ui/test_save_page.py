"""The Save (＋) tab: paste a link, platform detected, ingest, paste-text fallback.

Driven through the real entry file with AppTest and a stub API client that
records every call and answers the ingest/poll endpoints from a script. AppTest
sees elements and session state but not CSS or a real worker, so layout and the
real ingest are checked live instead.
"""

import time

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from app.ui import api

ENTRY = "app/ui/streamlit_app.py"
PAGE = "views/save.py"
OTHER_PAGE = "views/pantry.py"

SHORT = "youtube.com/shorts/aBcDeFgHiJk"
SHORT_FULL = "https://youtube.com/shorts/aBcDeFgHiJk"


class _StubClient:
    """POST /recipes/ingest returns a task id; GET .../{id} walks through `polls`."""

    def __init__(self, polls=None, post_status=202):
        self.polls = list(polls or [{"state": "success", "recipe": {"id": 7, "title": "Carbonara"}}])
        self.post_status = post_status
        self.posts = []
        self.gets = []

    def post(self, url, json=None, **kwargs):
        assert url == "/recipes/ingest"
        self.posts.append(json)
        request = httpx.Request("POST", "http://stub")
        if self.post_status >= 400:
            return httpx.Response(self.post_status, json={"detail": "nope"}, request=request)
        return httpx.Response(self.post_status, json={"task_id": "t1"}, request=request)

    def get(self, url, **kwargs):
        request = httpx.Request("GET", "http://stub")
        if url == "/recipes":  # the recipe page, once "Open recipe" has been tapped
            return httpx.Response(200, json=[], request=request)
        assert url == "/recipes/ingest/t1"
        self.gets.append(url)
        result = self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]
        return httpx.Response(200, json=result, request=request)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


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


def _type(at, value):
    at.text_input(key="save_url_widget").set_value(value).run()
    assert not at.exception


def _paste(at, value):
    at.text_area(key="save_paste_widget").set_value(value).run()
    assert not at.exception


def _save(at):
    at.button(key="save-submit").click().run()
    assert not at.exception


def _text(at) -> str:
    return "\n".join(
        el.value for el in [*at.markdown, *at.caption, *at.warning, *at.error, *at.success]
    )


def test_invalid_link_blocks_request(monkeypatch):
    at, client = _open(monkeypatch)

    _type(at, "chicken curry")
    _save(at)

    assert client.posts == []
    assert "That doesn't look like a link" in _text(at)
    assert not at.success


def test_non_http_scheme_blocks_request(monkeypatch):
    at, client = _open(monkeypatch)

    _type(at, "ftp://files.example.com/recipe")
    _save(at)

    assert client.posts == []
    assert "That doesn't look like a link" in _text(at)


def test_blank_submit_blocks_request(monkeypatch):
    at, client = _open(monkeypatch)

    _save(at)

    assert client.posts == []
    assert at.error


def test_detected_source_label_shown_for_shorts_url(monkeypatch):
    at, client = _open(monkeypatch)

    _type(at, SHORT)

    assert "YouTube link" in _text(at)
    assert client.posts == []  # shown before anything is submitted


@pytest.mark.parametrize(
    "link, label",
    [
        ("https://www.instagram.com/reel/abc/", "Instagram post"),
        ("seriouseats.com/pasta", "Website"),
    ],
)
def test_detected_source_label_for_other_platforms(monkeypatch, link, label):
    at, _ = _open(monkeypatch)

    _type(at, link)

    assert label in _text(at)


def test_ingest_payload_has_detected_platform_and_normalised_url(monkeypatch):
    at, client = _open(monkeypatch)

    _type(at, f"  {SHORT}  ")
    _save(at)

    assert client.posts == [{"source_platform": "youtube", "url": SHORT_FULL}]


def test_paste_text_included_in_payload(monkeypatch):
    at, client = _open(monkeypatch)

    _type(at, "https://www.instagram.com/reel/abc/")
    _paste(at, "2 eggs\nboil them")
    _save(at)

    assert client.posts == [
        {
            "source_platform": "instagram",
            "url": "https://www.instagram.com/reel/abc/",
            "caption_text": "2 eggs\nboil them",
        }
    ]


def test_blank_paste_box_sends_no_caption_text(monkeypatch):
    at, client = _open(monkeypatch)

    _type(at, SHORT)
    _paste(at, "   ")
    _save(at)

    assert "caption_text" not in client.posts[0]


def test_success_shows_open_recipe(monkeypatch):
    at, client = _open(monkeypatch)

    _type(at, SHORT)
    _save(at)

    assert "Added: Carbonara" in _text(at)
    assert at.button(key="save-open-recipe").label == "Open recipe"
    # Emptied so the same link isn't saved twice by a second tap.
    assert at.text_input(key="save_url_widget").value == ""


def test_polls_until_the_worker_finishes(monkeypatch):
    client = _StubClient(
        polls=[
            {"state": "pending"},
            {"state": "pending"},
            {"state": "success", "recipe": {"id": 7, "title": "Carbonara"}},
        ]
    )
    at, client = _open(monkeypatch, client)

    _type(at, SHORT)
    _save(at)

    assert len(client.gets) == 3
    assert "Added: Carbonara" in _text(at)


def test_open_recipe_button_goes_to_the_recipe_page(monkeypatch):
    at, _ = _open(monkeypatch)
    _type(at, SHORT)
    _save(at)

    # A rerun of its own (a button press), after the polling run has finished.
    at.button(key="save-open-recipe").click().run()

    assert not at.exception
    assert at.session_state["open_recipe_id"] == 7
    assert at.query_params["recipe"] == ["7"]


def test_title_is_escaped_in_the_success_message(monkeypatch):
    client = _StubClient(polls=[{"state": "success", "recipe": {"id": 7, "title": "*Spicy* [mix]"}}])
    at, _ = _open(monkeypatch, client)

    _type(at, SHORT)
    _save(at)

    assert "Added: \\*Spicy\\* \\[mix\\]" in _text(at)


def test_failed_fetch_stores_failure_and_opens_paste_box_with_reason(monkeypatch):
    client = _StubClient(polls=[{"state": "failure", "error": "Sign in to confirm you're not a bot"}])
    at, _ = _open(monkeypatch, client)

    _type(at, SHORT)
    _save(at)

    assert at.session_state["fetch_failure"] == {
        "platform": "youtube",
        "url": SHORT_FULL,
        "error": "Sign in to confirm you're not a bot",
    }
    assert "Sign in to confirm you're not a bot" in _text(at)
    assert "Paste the transcript instead" in [e.label for e in at.expander]
    assert at.expander[0].proto.expanded


def test_fetch_failure_opens_paste_box_with_reason(monkeypatch):
    failure = {"platform": "youtube", "url": SHORT_FULL, "error": "blocked"}
    at, _ = _open(monkeypatch, fetch_failure=failure, save_url=SHORT)

    assert "blocked" in _text(at)
    assert at.expander[0].proto.expanded


def test_failure_for_another_url_does_not_open_the_box(monkeypatch):
    failure = {"platform": "youtube", "url": "https://youtu.be/other", "error": "blocked"}
    at, _ = _open(monkeypatch, fetch_failure=failure, save_url=SHORT)

    assert "blocked" not in _text(at)
    assert not at.expander[0].proto.expanded


def test_failure_with_pasted_text_is_not_stored_as_a_fetch_failure(monkeypatch):
    client = _StubClient(polls=[{"state": "failure", "error": "no recipe in that text"}])
    at, _ = _open(monkeypatch, client)

    _type(at, SHORT)
    _paste(at, "just some words")
    _save(at)

    assert not at.session_state.filtered_state.get("fetch_failure")
    assert not at.success


def test_state_survives_switching_tabs_and_back(monkeypatch):
    failure = {"platform": "youtube", "url": SHORT_FULL, "error": "blocked"}
    at, _ = _open(monkeypatch, fetch_failure=failure, save_url=SHORT, save_paste="half typed")

    at.switch_page(OTHER_PAGE).run()
    assert not at.exception
    at.switch_page(PAGE).run()
    assert not at.exception

    assert at.text_input(key="save_url_widget").value == SHORT
    assert at.text_area(key="save_paste_widget").value == "half typed"
    assert "blocked" in _text(at)
    assert at.expander[0].proto.expanded


def test_saved_result_survives_switching_tabs_and_back(monkeypatch):
    at, _ = _open(monkeypatch, save_result={"id": 7, "title": "Carbonara"})

    at.switch_page(OTHER_PAGE).run()
    at.switch_page(PAGE).run()

    assert "Added: Carbonara" in _text(at)
    assert at.button(key="save-open-recipe").label == "Open recipe"


def test_api_error_on_submit_is_reported_inline(monkeypatch):
    at, client = _open(monkeypatch, _StubClient(post_status=422))

    _type(at, SHORT)
    _save(at)

    assert "nope" in _text(at)
    assert not at.success
