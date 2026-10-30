"""Save (＋) tab: paste a link, tap Save.

The source platform is detected from the URL (`logic.detect_platform`), so there
is no Source control; the detected source is shown under the box. Ingestion runs
on the Celery worker (ADR-0013): this page POSTs `/recipes/ingest`, then polls
`/recipes/ingest/{task_id}` every 2s inside `st.status`, for at most two minutes
(`api.INGEST_DEADLINE_SECONDS`) before saying it is still working.

The task being polled is kept in session state (`save_task`), written straight
after the POST. Streamlit acts on a tap only at an st call, by abandoning the
run there, so a tap on another tab mid-poll would otherwise lose the result, and
a second tap on Save would post the recipe again (the API doesn't dedupe). With
the task remembered, the next visit to Save resumes polling it, and Save stays
disabled until it resolves. Every outcome is likewise written to session state
before anything is drawn, then shown by a rerun.

Every source is fetched automatically. When that fails (YouTube's anti-bot check,
ADR-0024; a private or uncaptioned Instagram post, ADR-0030; a site that blocks
us or has no recipe on it, ADR-0031) the paste-text box opens with the reason, and
the URL stays in its field so the user only has to add the text.

Session keys, all plain so they outlive the widgets: `save_url`, `save_paste`
(the field contents), `fetch_failure` ({platform, url, error} of the last failed
automatic fetch), `save_result` ({id, title} of the last save; cleared by a new
link or by opening it), `save_error` (the last poll's error, or the deadline
message) and `save_task` ({task_id, platform, url, pasted, started}). The widgets
have their own `*_widget` keys and the plain keys mirror them, because Streamlit
forgets a widget's state on any run where the widget isn't drawn (e.g. while
another tab is showing) and the contents have to survive a tab switch.
"""

from typing import NoReturn

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
TIMED_OUT = (
    "Still working… check the Recipes tab in a minute. If it never shows up, "
    "try again or paste the text instead."
)


def _submit(client: httpx.Client, platform: str, url: str, caption_text: str) -> None:
    """POST the recipe and remember the task; polling it is `_poll`'s job.

    A rejected POST is reported inline and nothing is remembered.
    """
    payload = {"source_platform": platform, "url": url}
    if caption_text:
        payload["caption_text"] = caption_text
    try:
        response = client.post("/recipes/ingest", json=payload)
        response.raise_for_status()
        task_id = response.json()["task_id"]
    except httpx.HTTPStatusError as exc:
        st.error(components.md_escape(f"Couldn't submit this recipe: {api.error_detail(exc)}"))
        return
    except httpx.HTTPError as exc:
        st.error(components.md_escape(f"Request failed: {exc}"))
        return
    # Stored before any other st call. Streamlit acts on a tap (another tab, or
    # Save again) only at an st call, by abandoning this run there; from here on
    # an abandoned run leaves the task behind for the next run to pick up,
    # instead of losing it (and, for a second tap on Save, posting it again).
    st.session_state.save_task = {
        "task_id": task_id,
        "platform": platform,
        "url": url,
        "pasted": bool(caption_text),
        "started": api.now(),
    }


def _finish(**state) -> NoReturn:
    """The task resolved (or was given up on): record the outcome and rerun.

    The outcome goes into session state before any st call, so a tap that
    abandons the run can't lose it; the rerun then draws it.
    """
    st.session_state.save_task = None
    st.session_state.save_error = None
    for key, value in state.items():
        st.session_state[key] = value
    st.rerun()


def _poll(client: httpx.Client, task: dict) -> None:
    """Poll the worker (ADR-0013) until the task resolves or the deadline passes.

    Always polls at least once, so a task that finished while the user was on
    another tab is reported even if that took longer than the deadline.
    """
    with st.status("Parsing recipe...") as status:
        while True:
            try:
                poll = client.get(f"/recipes/ingest/{task['task_id']}")
                poll.raise_for_status()
                result = poll.json()
            except httpx.HTTPError as exc:
                _finish(save_error=f"Request failed: {exc}")

            if result["state"] == "success":
                recipe = result["recipe"]
                _finish(
                    save_result={"id": recipe["id"], "title": recipe["title"]},
                    fetch_failure=None,
                    save_clear_inputs=True,
                )
            if result["state"] == "failure":
                # Only an automatic fetch can be rescued by pasting; pasted
                # text that failed to parse already took that route.
                if task["pasted"]:
                    _finish(save_error=f"Couldn't parse this recipe: {result['error']}")
                _finish(
                    fetch_failure={
                        "platform": task["platform"], "url": task["url"], "error": result["error"],
                    }
                )
            elapsed = api.now() - task["started"]
            if elapsed >= api.INGEST_DEADLINE_SECONDS:
                _finish(save_error=TIMED_OUT)
            # An st call every round, so a tap on another tab is acted on now,
            # not when the worker finishes; the task outlives the abandoned run.
            status.update(label=f"Parsing recipe... ({int(elapsed)}s)")
            api.sleep(api.INGEST_POLL_SECONDS)


# After a save the fields are emptied so a second tap can't save the same link
# twice. Done at the top of the next run, before the widgets exist.
if st.session_state.pop("save_clear_inputs", False):
    # Assigned to the widget keys (not just popped): that is what makes the
    # browser replace the text it is showing, rather than keep it.
    st.session_state.save_url = st.session_state.save_url_widget = ""
    st.session_state.save_paste = st.session_state.save_paste_widget = ""

st.subheader("Save a recipe")
previous_url = st.session_state.get("save_url", "")
raw_url = st.text_input(
    "Link",
    value=previous_url,
    key="save_url_widget",
    placeholder="Paste a YouTube, Instagram or recipe link",
)
st.session_state.save_url = raw_url
if raw_url.strip() and raw_url != previous_url:
    # A new link: the last save's banner (or error) is about something else now.
    st.session_state.save_result = None
    st.session_state.save_error = None
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
        f"Couldn't fetch this {noun} automatically: {components.md_escape(failure['error'])}\n\n"
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

# While a task is being polled, Save is disabled - and a tap that was already
# on its way (its trigger arrives with the next run) is ignored, not re-posted.
task = st.session_state.get("save_task")
if st.button(
    "Save recipe", key="save-submit", type="primary", width="stretch", disabled=task is not None
) and task is None:
    if url is None:
        # A non-blank invalid value already has the warning above.
        if not raw_url.strip():
            st.error("Paste a link first")
    else:
        st.session_state.save_result = None
        st.session_state.save_error = None
        client = api.get_client()
        _submit(client, platform, url, pasted.strip())
        task = st.session_state.get("save_task")
        if task is not None:
            _poll(client, task)
elif task is not None:
    # A run abandoned mid-poll (a tap elsewhere) left this behind: carry on.
    _poll(api.get_client(), task)

error = st.session_state.get("save_error")
if error:
    st.error(components.md_escape(error))

saved = st.session_state.get("save_result")
if saved:
    st.success(f"Added: {components.md_escape(saved['title'])}")
    # A button handled in the script body, not an on_click: inside a callback
    # Streamlit turns the page switch into a no-op (see nav.open_recipe).
    if st.button("Open recipe", key="save-open-recipe", width="stretch"):
        st.session_state.save_result = None  # don't greet the user with it on return
        nav.open_recipe(saved["id"])
