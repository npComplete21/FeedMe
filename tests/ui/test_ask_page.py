"""The Ask tab: a chat with the recipe assistant.

Driven through the real entry file with AppTest and a stub API client that records
every POST /chat. AppTest sees elements and session state but not CSS, so the
chat input sitting above the tab bar is checked live instead.
"""

import copy

import httpx
from streamlit.testing.v1 import AppTest

from app.ui import api

ENTRY = "app/ui/streamlit_app.py"
PAGE = "views/ask.py"
OTHER_PAGE = "views/save.py"


class _StubClient:
    """POST /chat answers with a numbered reply and a growing opaque history.

    Records a deep copy of every payload (the page hands over its live list).
    """

    def __init__(self, post_status=200, error=None):
        self.post_status = post_status
        self.error = error
        self.posts = []

    def post(self, url, json=None, **kwargs):
        assert url == "/chat"
        self.posts.append(copy.deepcopy(json))
        if self.error:
            raise self.error
        request = httpx.Request("POST", "http://stub")
        if self.post_status >= 400:
            return httpx.Response(self.post_status, json={"detail": "nope"}, request=request)
        n = len(self.posts)
        reply = f"reply {n}"
        history = json["history"] + [
            {"role": "user", "content": json["message"]},
            {"role": "assistant", "content": reply},
        ]
        return httpx.Response(200, json={"reply": reply, "history": history}, request=request)

    def get(self, url, **kwargs):  # the Save tab, when a test switches to it
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


def _say(at, text):
    at.chat_input[0].set_value(text).run()
    assert not at.exception


def _text(at):
    return "\n".join(el.value for el in [*at.markdown, *at.info, *at.error, *at.caption, *at.warning])


def _bubbles(at):
    return [(m.name, m.markdown[0].value) for m in at.chat_message]


def test_chat_posts_message_with_history_and_appends_reply(monkeypatch):
    at, client = _open(monkeypatch)

    _say(at, "I have eggs")
    _say(at, "and cheese?")

    assert client.posts[0] == {"message": "I have eggs", "history": []}
    # The second turn replays the opaque history returned by the first.
    assert client.posts[1] == {
        "message": "and cheese?",
        "history": [
            {"role": "user", "content": "I have eggs"},
            {"role": "assistant", "content": "reply 1"},
        ],
    }
    assert _bubbles(at) == [
        ("user", "I have eggs"),
        ("assistant", "reply 1"),
        ("user", "and cheese?"),
        ("assistant", "reply 2"),
    ]
    assert at.session_state["chat_display"] == [
        ("user", "I have eggs"),
        ("assistant", "reply 1"),
        ("user", "and cheese?"),
        ("assistant", "reply 2"),
    ]
    assert len(at.session_state["chat_history"]) == 4


def test_chat_error_shown_inline_and_history_unchanged(monkeypatch):
    client = _StubClient()
    at, _ = _open(monkeypatch, client)
    _say(at, "first")
    before = copy.deepcopy(at.session_state["chat_history"])

    client.post_status = 500
    _say(at, "second")

    assert [e.value for e in at.error] == ["Couldn't respond: nope"]
    # The provider history is untouched: no half-appended turn to replay.
    assert at.session_state["chat_history"] == before
    # The question stays on screen, without a reply.
    assert at.session_state["chat_display"][-1] == ("user", "second")

    # The next turn replays only the successful history.
    client.post_status = 200
    _say(at, "third")
    assert client.posts[-1]["history"] == before


def test_transport_error_shown_inline_and_history_unchanged(monkeypatch):
    client = _StubClient(error=httpx.ConnectError("boom"))
    at, _ = _open(monkeypatch, client)

    _say(at, "hello")

    assert [e.value for e in at.error] == ["Request failed: boom"]
    assert at.session_state["chat_history"] == []


def test_error_text_is_escaped(monkeypatch):
    at, _ = _open(monkeypatch, _StubClient(error=httpx.ConnectError("a *b* [c](d)")))

    _say(at, "hello")

    assert at.error[0].value == r"Request failed: a \*b\* \[c\]\(d\)"


def test_users_own_message_is_not_rendered_as_markdown(monkeypatch):
    at, _ = _open(monkeypatch)

    _say(at, "**bold** [x](http://evil)")

    assert _bubbles(at)[0] == ("user", r"\*\*bold\*\* \[x\]\(http://evil\)")


def test_new_chat_clears_state(monkeypatch):
    at, client = _open(monkeypatch)
    _say(at, "I have eggs")

    at.button(key="ask-new-chat").click().run()

    assert not at.exception
    assert at.session_state["chat_history"] == []
    assert at.session_state["chat_display"] == []
    assert _bubbles(at) == []
    assert "chicken, rice and broccoli" in _text(at)
    # And the next message starts from an empty history again.
    _say(at, "again")
    assert client.posts[-1]["history"] == []


def test_empty_state_hint_and_no_new_chat_button_on_a_fresh_session(monkeypatch):
    at, client = _open(monkeypatch)

    assert "chicken, rice and broccoli" in _text(at)
    assert [b.key for b in at.button if b.key == "ask-new-chat"] == []
    assert client.posts == []


def test_hint_goes_away_once_the_conversation_starts(monkeypatch):
    at, _ = _open(monkeypatch)

    _say(at, "I have eggs")

    assert "chicken, rice and broccoli" not in _text(at)
    assert [b.key for b in at.button if b.key == "ask-new-chat"] == ["ask-new-chat"]


def test_conversation_survives_switching_tabs(monkeypatch):
    at, client = _open(monkeypatch)
    _say(at, "I have eggs")

    at.switch_page(OTHER_PAGE).run()
    assert not at.exception
    at.switch_page(PAGE).run()
    assert not at.exception

    assert _bubbles(at) == [("user", "I have eggs"), ("assistant", "reply 1")]
    assert len(client.posts) == 1
    # ...and the replayed history still goes with the next turn.
    _say(at, "more")
    assert len(client.posts[-1]["history"]) == 2
