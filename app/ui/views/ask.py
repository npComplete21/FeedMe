"""Ask tab: chat with an assistant that knows your recipes.

POSTs `/chat` with `{"message", "history"}`; the reply carries `reply` (text to
show) and `history` (the provider's own message list, opaque to us).

Session keys, both plain so they outlive the tab being left:
- `chat_history`: that opaque provider history. The API is stateless, so the
  whole thing is sent back on every turn. It is only ever replaced by a
  successful response, so a failed request never leaves a half-turn in it.
- `chat_display`: `[(role, text)]` for rendering. A failed request still adds
  the user's question here (so it stays on screen), but not to `chat_history`.

The chat input sits above the fixed tab bar via the `stBottomBlockContainer`
rule in `app.ui.nav`; AppTest can't see CSS, so that is checked live.
"""

import httpx
import streamlit as st

from app.ui import api, components

EXAMPLE = "I have chicken, rice and broccoli — what should I make?"


def _ask(prompt: str) -> None:
    """Send one turn; on success store the reply and the new history.

    A failure is shown inline and changes nothing in `chat_history`.
    """
    try:
        response = api.get_client().post(
            "/chat", json={"message": prompt, "history": st.session_state.chat_history}
        )
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as exc:
        st.error(components.md_escape(f"Couldn't respond: {api.error_detail(exc)}"))
        return
    except httpx.HTTPError as exc:
        st.error(components.md_escape(f"Request failed: {exc}"))
        return
    st.session_state.chat_history = body["history"]
    st.session_state.chat_display.append(("assistant", body["reply"]))
    st.markdown(body["reply"])


def _new_chat() -> None:
    st.session_state.chat_history = []
    st.session_state.chat_display = []


st.session_state.setdefault("chat_history", [])
st.session_state.setdefault("chat_display", [])

prompt = st.chat_input("Ask about your recipes")
if prompt:
    st.session_state.chat_display.append(("user", prompt))

with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
    st.subheader("Ask")
    if st.session_state.chat_display:
        st.button("New chat", key="ask-new-chat", icon=":material/add_comment:", type="tertiary", on_click=_new_chat)

if not st.session_state.chat_display:
    st.caption(f"Ask what to cook from your saved recipes. Try: “{EXAMPLE}”")

for role, text in st.session_state.chat_display:
    with st.chat_message(role):
        # The user's own words are plain text; the assistant's reply is markdown.
        st.markdown(components.md_escape(text) if role == "user" else text)

if prompt:
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            _ask(prompt)
