"""Save (＋) tab: paste a link, tap Save.

The source platform is detected from the URL (`logic.detect_platform`), so there
is no Source control; the detected source is shown under the box. Ingestion runs
on the Celery worker (ADR-0013): this page POSTs `/recipes/ingest`, then polls
`/recipes/ingest/{task_id}` every 2s inside `st.status`.

Every source is fetched automatically. When that fails (YouTube's anti-bot check,
ADR-0024; a private or uncaptioned Instagram post, ADR-0030; a site that blocks
us or has no recipe on it, ADR-0031) the paste-text box opens with the reason, and
the URL stays in its field so the user only has to add the text.

Session keys, all plain so they outlive the widgets: `save_url`, `save_paste`
(the field contents), `fetch_failure` ({platform, url, error} of the last failed
automatic fetch) and `save_result` ({id, title} of the last save). The widgets
have their own `*_widget` keys and the plain keys mirror them, because Streamlit
forgets a widget's state on any run where the widget isn't drawn (e.g. while
another tab is showing) and the contents have to survive a tab switch.
"""

import time

import httpx
import streamlit as st

from app.ui import api, components, logic, nav

SOURCE_LABELS = {
    "youtube": "YouTube link",
    "instagram": "Instagram post",
    "website": "Website",
}

# platform -> (noun, expander label, text label, what to paste)
PASTE_COPY = {
    "youtube": (
        "video", "Paste the transcript instead", "Transcript or description text",
        "the transcript (or the recipe from the video's description)",
    ),
    "instagram": (
        "post", "Paste the caption instead", "Caption text", "the post's caption",
    ),
    "website": (
        "page", "Paste the recipe instead", "Recipe text",
        "the recipe's ingredients and steps",
    ),
}

NOT_A_LINK = "That doesn't look like a link"


def _submit(client: httpx.Client, platform: str, url: str, caption_text: str) -> None:
    """POST the recipe and poll the worker until it resolves.

    Success stores `save_result` and reruns (the inputs are cleared there); a
    failure of an automatic fetch stores `fetch_failure` and reruns so the paste
    box opens with the reason. Anything else is reported inline.
    """
    payload = {"source_platform": platform, "url": url}
    if caption_text:
        payload["caption_text"] = caption_text
    try:
        response = client.post("/recipes/ingest", json=payload)
        response.raise_for_status()
        task_id = response.json()["task_id"]
    except httpx.HTTPStatusError as exc:
        st.error(f"Couldn't submit this recipe: {api.error_detail(exc)}")
        return
    except httpx.HTTPError as exc:
        st.error(f"Request failed: {exc}")
        return

    # Ingestion runs on a background worker (Celery + Redis, see ADR-0013) -
    # poll for completion instead of blocking on one call.
    saved = None
    fetch_failure = None
    with st.status("Parsing recipe...") as status:
        while True:
            try:
                poll = client.get(f"/recipes/ingest/{task_id}")
                poll.raise_for_status()
                result = poll.json()
            except httpx.HTTPError as exc:
                status.update(label=f"Request failed: {exc}", state="error")
                break

            if result["state"] == "success":
                recipe = result["recipe"]
                status.update(label="Saved", state="complete")
                saved = {"id": recipe["id"], "title": recipe["title"]}
                break
            if result["state"] == "failure":
                status.update(
                    label=f"Couldn't parse this recipe: {result['error']}", state="error"
                )
                # Only an automatic fetch can be rescued by pasting; pasted
                # text that failed to parse already took that route.
                if not caption_text:
                    fetch_failure = {"platform": platform, "url": url, "error": result["error"]}
                break
            time.sleep(2)

    if saved:
        st.session_state.save_result = saved
        st.session_state.fetch_failure = None
        st.session_state.save_clear_inputs = True
        st.rerun()
    if fetch_failure:
        st.session_state.fetch_failure = fetch_failure
        st.rerun()


# After a save the fields are emptied so a second tap can't save the same link
# twice. Done at the top of the next run, before the widgets exist.
if st.session_state.pop("save_clear_inputs", False):
    # Assigned to the widget keys (not just popped): that is what makes the
    # browser replace the text it is showing, rather than keep it.
    st.session_state.save_url = st.session_state.save_url_widget = ""
    st.session_state.save_paste = st.session_state.save_paste_widget = ""

st.subheader("Save a recipe")
raw_url = st.text_input(
    "Link",
    value=st.session_state.get("save_url", ""),
    key="save_url_widget",
    placeholder="Paste a YouTube, Instagram or recipe link",
)
st.session_state.save_url = raw_url
url = logic.normalize_url(raw_url)
platform = logic.detect_platform(url) if url else "website"

if url:
    st.caption(f"Detected: {SOURCE_LABELS[platform]}")
elif raw_url.strip():
    st.warning(NOT_A_LINK)

noun, expander_label, text_label, what_to_paste = PASTE_COPY[platform]
failure = st.session_state.get("fetch_failure")
fetch_failed = (
    url is not None
    and failure is not None
    and (failure["platform"], failure["url"]) == (platform, url)
)
if fetch_failed:
    st.warning(
        f"Couldn't fetch this {noun} automatically: {failure['error']}\n\n"
        f"Paste {what_to_paste} below instead."
    )
with st.expander(expander_label, expanded=fetch_failed):
    pasted = st.text_area(
        text_label,
        value=st.session_state.get("save_paste", ""),
        key="save_paste_widget",
        help=f"Optional. If filled in, this is used instead of fetching the {noun}.",
    )
st.session_state.save_paste = pasted

if st.button("Save recipe", key="save-submit", type="primary", width="stretch"):
    if url is None:
        # A non-blank invalid value already has the warning above.
        if not raw_url.strip():
            st.error("Paste a link first")
    else:
        st.session_state.save_result = None
        _submit(api.get_client(), platform, url, pasted.strip())

saved = st.session_state.get("save_result")
if saved:
    st.success(f"Added: {components.md_escape(saved['title'])}")
    # A button handled in the script body, not an on_click: inside a callback
    # Streamlit turns the page switch into a no-op (see nav.open_recipe).
    if st.button("Open recipe", key="save-open-recipe", width="stretch"):
        nav.open_recipe(saved["id"])
