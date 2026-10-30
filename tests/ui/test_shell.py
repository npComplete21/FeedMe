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

    assert not (Path(ENTRY).parent / "pages").exists()
