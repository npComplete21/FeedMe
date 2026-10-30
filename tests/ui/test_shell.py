"""The app shell: login gate, hidden navigation, bottom tab bar, global 401.

AppTest can see the elements a run produces (tabs, page links, session state)
but not CSS, so the bar being fixed to the bottom is checked live instead.
"""

import httpx
from streamlit.testing.v1 import AppTest

from app.ui import api

ENTRY = "app/ui/streamlit_app.py"


class _StubClient:
    """Stands in for the httpx client: every GET returns an empty list."""

    def get(self, *args, **kwargs):
        return httpx.Response(200, json=[], request=httpx.Request("GET", "http://stub"))

    def post(self, *args, **kwargs):
        return httpx.Response(200, json={}, request=httpx.Request("POST", "http://stub"))


def _tab_bar_links(at: AppTest) -> list:
    return [link.proto for link in at.get("page_link")]


def test_logged_out_shows_login_not_tabs():
    at = AppTest.from_file(ENTRY).run()

    assert not at.exception
    assert [tab.label for tab in at.tabs] == ["Log in", "Register"]
    assert any(button.label == "Log in" for button in at.button)
    assert _tab_bar_links(at) == []


def test_logged_in_renders_four_tabs(monkeypatch):
    monkeypatch.setattr(api, "get_client", lambda: _StubClient())
    at = AppTest.from_file(ENTRY)
    at.session_state["access_token"] = "t"
    at.session_state["user_email"] = "cook@example.com"
    at.run()

    assert not at.exception
    links = _tab_bar_links(at)
    labels = [link.label for link in links]
    assert labels[0] == "Recipes"
    assert labels[1] == "Pantry"
    assert "Save" in labels[2]
    assert labels[3] == "Ask"
    assert len(labels) == 4
    assert not any("Plan" in label for label in labels)
    # The login screen is gone once there is a token.
    assert not any(tab.label == "Log in" for tab in at.tabs)


def test_logged_in_lands_on_recipes_by_default(monkeypatch):
    monkeypatch.setattr(api, "get_client", lambda: _StubClient())
    at = AppTest.from_file(ENTRY)
    at.session_state["access_token"] = "t"
    at.session_state["user_email"] = "cook@example.com"
    at.run()

    # The Recipes page ran: its search box is there (the stub library is empty).
    assert [ti.key for ti in at.text_input] == ["recipes_query_widget"]


def _script_that_gets_a_401():
    # Runs as its own little Streamlit script under AppTest: a real client from
    # api.get_client(), talking to a transport that always answers 401.
    import httpx
    import streamlit as st

    from app.ui import api

    if st.session_state.get("access_token"):
        transport = httpx.MockTransport(lambda request: httpx.Response(401))
        api.get_client(transport=transport).get("/recipes")
        st.write("not reached")
    else:
        st.write("logged out")


def test_401_logs_out():
    at = AppTest.from_function(_script_that_gets_a_401)
    at.session_state["access_token"] = "expired"
    at.session_state["user_email"] = "cook@example.com"
    at.run()

    assert not at.exception
    assert at.session_state["access_token"] is None
    assert at.session_state["user_email"] is None
    # A stale cookie snapshot must not log the session straight back in.
    assert at.session_state["ignore_remembered_token"] is True
    assert [md.value for md in at.markdown] == ["logged out"]


def _script_that_logs_out():
    import streamlit as st

    from app.ui import auth

    if st.session_state.get("access_token"):
        auth.log_out()


def test_log_out_clears_every_trace_of_the_previous_user():
    at = AppTest.from_function(_script_that_logs_out)
    at.session_state["access_token"] = "t"
    at.session_state["user_email"] = "a@example.com"
    at.session_state["chat_display"] = [("user", "secret question")]
    at.session_state["chat_history"] = [{"role": "user", "content": "secret question"}]
    at.session_state["pantry_results"] = {"pantry": ["egg"], "matches": []}
    at.session_state["save_result"] = {"id": 7, "title": "Carbonara"}
    at.session_state["recipes_query"] = "carbonara"
    at.session_state["open_recipe_id"] = 7
    at.session_state["editing-7"] = True
    at.run()

    assert not at.exception
    state = at.session_state.filtered_state
    for key in (
        "chat_display", "chat_history", "pantry_results", "save_result",
        "recipes_query", "open_recipe_id", "editing-7",
    ):
        assert key not in state, key
    assert at.session_state["access_token"] is None
    assert at.session_state["ignore_remembered_token"] is True


def _fake_login(monkeypatch, email):
    from app.ui import auth

    def post(url, json=None, **kwargs):
        assert url.endswith("/auth/login")
        return httpx.Response(
            200, json={"access_token": f"token-for-{email}"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(auth.httpx, "post", post)


def test_logging_out_and_in_as_someone_else_starts_with_an_empty_chat(monkeypatch):
    monkeypatch.setattr(api, "get_client", lambda: _StubClient())
    at = AppTest.from_file(ENTRY, default_timeout=10)
    at.session_state["access_token"] = "t"
    at.session_state["user_email"] = "a@example.com"
    at.session_state["chat_display"] = [("user", "secret question"), ("assistant", "an answer")]
    at.session_state["chat_history"] = [{"role": "user", "content": "secret question"}]
    at.switch_page("views/ask.py")
    at.run()
    assert [m.name for m in at.chat_message] == ["user", "assistant"]

    next(b for b in at.button if b.label == "Log out").click().run()
    assert not at.exception
    assert [tab.label for tab in at.tabs] == ["Log in", "Register"]

    _fake_login(monkeypatch, "b@example.com")
    at.text_input[0].set_value("b@example.com")
    at.text_input[1].set_value("pw")
    next(b for b in at.button if b.label == "Log in").click().run()
    assert not at.exception
    at.switch_page("views/ask.py").run()

    assert not at.exception
    assert at.session_state["user_email"] == "b@example.com"
    assert list(at.chat_message) == []
    assert any("Ask what to cook" in c.value for c in at.caption)


def test_logging_in_clears_state_left_over_without_a_log_out(monkeypatch):
    # e.g. a remembered cookie for a different user restored into a session
    # that still holds someone's state: whoever logs in starts clean.
    monkeypatch.setattr(api, "get_client", lambda: _StubClient())
    at = AppTest.from_file(ENTRY, default_timeout=10)
    at.session_state["pantry_results"] = {"pantry": ["egg"], "matches": []}
    at.session_state["chat_display"] = [("user", "secret question")]
    at.run()
    _fake_login(monkeypatch, "b@example.com")
    at.text_input[0].set_value("b@example.com")
    at.text_input[1].set_value("pw")
    next(b for b in at.button if b.label == "Log in").click().run()

    assert not at.exception
    state = at.session_state.filtered_state
    assert at.session_state["user_email"] == "b@example.com"
    assert "pantry_results" not in state
    assert "chat_display" not in state


def test_client_sends_bearer_token():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=[])

    def script():
        import httpx
        import streamlit as st

        from app.ui import api

        api.get_client(transport=st.session_state.transport).get("/recipes")

    at = AppTest.from_function(script)
    at.session_state["access_token"] = "abc"
    at.session_state["transport"] = httpx.MockTransport(handler)
    at.run()

    assert not at.exception
    assert seen["auth"] == "Bearer abc"


def test_error_detail_prefers_detail_field():
    response = httpx.Response(
        404, json={"detail": "Recipe not found"}, request=httpx.Request("GET", "http://x")
    )
    exc = httpx.HTTPStatusError("boom", request=response.request, response=response)
    assert api.error_detail(exc) == "Recipe not found"


def test_error_detail_without_detail_field_returns_body():
    response = httpx.Response(404, json={"other": "x"}, request=httpx.Request("GET", "http://x"))
    exc = httpx.HTTPStatusError("boom", request=response.request, response=response)
    assert api.error_detail(exc) == response.text


def test_error_detail_falls_back_to_text_for_non_json():
    response = httpx.Response(502, text="Bad gateway", request=httpx.Request("GET", "http://x"))
    exc = httpx.HTTPStatusError("boom", request=response.request, response=response)
    assert api.error_detail(exc) == "Bad gateway"


def test_no_pages_folder_next_to_entry_file():
    # A `pages/` folder beside the entry file switches on Streamlit's legacy
    # folder navigation on any run that hasn't called st.navigation yet (e.g.
    # the first request after a restart), exposing every file by URL. Screens
    # live in app/ui/views/ instead.
    from pathlib import Path

    entry = Path(__file__).resolve().parents[2] / ENTRY
    assert entry.exists()
    assert not (entry.parent / "pages").exists()
