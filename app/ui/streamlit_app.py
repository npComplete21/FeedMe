import base64
import json
import os
import time

import httpx
import streamlit as st
from dotenv import load_dotenv

from app.ui.vocabulary import CUISINES, MEAL_TYPES

load_dotenv()

API_BASE_URL = os.environ.get("FEEDME_API_URL", "http://localhost:8000")

st.set_page_config(page_title="FeedMe", page_icon="🍳")

if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None

# Remembering a login across closed tabs (ADR-0029). The JWT is kept in a
# browser cookie; Streamlit can read cookies (st.context.cookies) but has no API
# to write one, so writes go through a tiny script on the next page render.
TOKEN_COOKIE = "feedme_token"
if "pending_cookie_script" not in st.session_state:
    st.session_state.pending_cookie_script = None
# st.context.cookies is a snapshot from when this tab connected, so after a
# logout it still holds the old token - without this flag the session would
# immediately log itself back in from that stale snapshot.
if "ignore_remembered_token" not in st.session_state:
    st.session_state.ignore_remembered_token = False


def _token_seconds_left(token: str) -> int:
    """Seconds until the JWT's own `exp`, so the cookie never outlives the token.
    Read without verifying the signature - the API verifies; this is only a TTL."""
    try:
        segment = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
        return max(0, int(claims["exp"] - time.time()))
    except (IndexError, KeyError, TypeError, ValueError):
        return 0


def _cookie_script(value: str, max_age: int) -> str:
    # json.dumps quotes and escapes the value for the JS string literal.
    return (
        "<script>document.cookie = "
        f"{json.dumps(TOKEN_COOKIE)} + '=' + {json.dumps(value)} + "
        f"'; Max-Age={max_age}; Path=/; SameSite=Strict' + "
        "(location.protocol === 'https:' ? '; Secure' : '');</script>"
    )


def _log_in(token: str, email: str) -> None:
    st.session_state.access_token = token
    st.session_state.user_email = email
    st.session_state.ignore_remembered_token = False
    st.session_state.pending_cookie_script = _cookie_script(token, _token_seconds_left(token))


def _log_out() -> None:
    st.session_state.access_token = None
    st.session_state.user_email = None
    st.session_state.ignore_remembered_token = True
    st.session_state.pending_cookie_script = _cookie_script("", 0)


def _restore_remembered_login() -> None:
    if st.session_state.access_token or st.session_state.ignore_remembered_token:
        return
    token = st.context.cookies.get(TOKEN_COOKIE)
    if not token:
        return
    try:
        response = httpx.get(
            f"{API_BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.HTTPError:
        return  # API unreachable - show the login screen, keep the cookie for next time
    if response.status_code == 200:
        st.session_state.access_token = token
        st.session_state.user_email = response.json()["email"]
    elif response.status_code == 401:
        _log_out()  # expired or revoked - drop the cookie too


_restore_remembered_login()
if st.session_state.pending_cookie_script:
    # Emitted on a run that doesn't immediately st.rerun(), so it reaches the browser.
    st.html(st.session_state.pending_cookie_script, unsafe_allow_javascript=True)
    st.session_state.pending_cookie_script = None


def _error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        return exc.response.json().get("detail", exc.response.text)
    except ValueError:
        return exc.response.text


def _show_login_screen() -> None:
    st.title("FeedMe")
    login_tab, register_tab = st.tabs(["Log in", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in"):
                try:
                    response = httpx.post(
                        f"{API_BASE_URL}/auth/login",
                        json={"email": email, "password": password},
                        timeout=30,
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    st.error(_error_detail(exc))
                except httpx.HTTPError as exc:
                    st.error(f"Request failed: {exc}")
                else:
                    _log_in(response.json()["access_token"], email)
                    st.rerun()

    with register_tab:
        with st.form("register_form"):
            email = st.text_input("Email", key="register_email")
            password = st.text_input("Password", type="password", key="register_password")
            registration_code = st.text_input("Registration code")
            if st.form_submit_button("Register"):
                try:
                    response = httpx.post(
                        f"{API_BASE_URL}/auth/register",
                        json={
                            "email": email,
                            "password": password,
                            "registration_code": registration_code,
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    st.error(_error_detail(exc))
                except httpx.HTTPError as exc:
                    st.error(f"Request failed: {exc}")
                else:
                    _log_in(response.json()["access_token"], email)
                    st.rerun()


if not st.session_state.access_token:
    _show_login_screen()
    st.stop()


def _handle_response(response: httpx.Response) -> None:
    # Global 401 handler: an expired or invalidated token drops the user
    # back to the login screen, instead of every call site below needing
    # its own expiry check.
    if response.status_code == 401:
        _log_out()
        st.rerun()


client = httpx.Client(
    base_url=API_BASE_URL,
    timeout=60.0,
    headers={"Authorization": f"Bearer {st.session_state.access_token}"},
    event_hooks={"response": [_handle_response]},
)

st.title("FeedMe")
header_cols = st.columns([5, 1])
with header_cols[0]:
    # Code span, not an f-string with the raw address - otherwise Streamlit's
    # markdown renderer autolinks the email into a clickable mailto: link.
    st.caption(f"Logged in as `{st.session_state.user_email}`")
with header_cols[1]:
    if st.button("Log out"):
        _log_out()
        st.rerun()


def _ingredients_to_text(ingredients: list[dict]) -> str:
    lines = []
    for ing in ingredients:
        lines.append(f"{ing['name']}, {ing['quantity']}" if ing.get("quantity") else ing["name"])
    return "\n".join(lines)


def _parse_ingredients_text(text: str) -> list[dict]:
    parsed = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "," in line:
            name, quantity = line.split(",", 1)
            parsed.append({"name": name.strip(), "quantity": quantity.strip() or None})
        else:
            parsed.append({"name": line, "quantity": None})
    return parsed


def _select_index(options_with_sentinel: list[str], current_value: str | None) -> int:
    if current_value in options_with_sentinel:
        return options_with_sentinel.index(current_value)
    return 0


st.header("Add a recipe")
source_platform = st.radio("Source", ["youtube", "instagram", "website"], horizontal=True)
url = st.text_input("URL")
caption_text = None
fetch_warning = st.empty()  # cleared below once a pasted caption succeeds

# Every source is fetched automatically; when that fails (YouTube's anti-bot
# check, ADR-0024; a private or uncaptioned Instagram post, ADR-0030; a site that
# blocks us or has no recipe on it, ADR-0031) for this
# same URL, open the paste box and say why - the URL field keeps its value, so
# the user only has to add the text.
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
noun, expander_label, text_label, what_to_paste = PASTE_COPY[source_platform]
failure = st.session_state.get("fetch_failure")
fetch_failed = (
    bool(url)
    and failure is not None
    and (failure["platform"], failure["url"]) == (source_platform, url)
)
if fetch_failed:
    fetch_warning.warning(
        f"Couldn't fetch this {noun} automatically: {failure['error']}\n\n"
        f"Paste {what_to_paste} below instead."
    )
with st.expander(expander_label, expanded=fetch_failed):
    caption_text = st.text_area(
        text_label,
        key=f"paste-{source_platform}",
        help=f"Optional. If filled in, this is used instead of fetching the {noun}.",
    )

if st.button("Ingest recipe"):
    if not url:
        st.error("URL is required")
    else:
        payload = {"source_platform": source_platform, "url": url}
        if caption_text:
            payload["caption_text"] = caption_text
        try:
            response = client.post("/recipes/ingest", json=payload)
            response.raise_for_status()
            task_id = response.json()["task_id"]
        except httpx.HTTPStatusError as exc:
            st.error(f"Couldn't submit this recipe: {_error_detail(exc)}")
        except httpx.HTTPError as exc:
            st.error(f"Request failed: {exc}")
        else:
            # Ingestion now runs on a background worker (Celery + Redis, see
            # ADR-0013) - poll for completion instead of blocking on one call.
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
                        status.update(
                            label=f"Added: {result['recipe']['title']}", state="complete"
                        )
                        st.session_state.fetch_failure = None
                        fetch_warning.empty()
                        break
                    if result["state"] == "failure":
                        status.update(
                            label=f"Couldn't parse this recipe: {result['error']}", state="error"
                        )
                        # Only an automatic fetch can be rescued by pasting; pasted
                        # text that failed to parse already took that route.
                        if not caption_text:
                            fetch_failure = {
                                "platform": source_platform,
                                "url": url,
                                "error": result["error"],
                            }
                        break
                    time.sleep(2)
            if fetch_failure:
                st.session_state.fetch_failure = fetch_failure
                st.rerun()

st.header("What can I make?")
pantry_text = st.text_input("Ingredients you have (comma-separated)")
if st.button("Find recipes"):
    pantry = [item.strip() for item in pantry_text.split(",") if item.strip()]
    matches = []
    try:
        response = client.post("/match", json={"pantry": pantry})
        response.raise_for_status()
        matches = response.json()
    except httpx.HTTPError as exc:
        st.error(f"Request failed: {exc}")

    if not matches:
        st.write("No matches.")
    for match in matches:
        recipe = match["recipe"]
        with st.expander(f"{recipe['title']} — {match['match_ratio']:.0%} match"):
            st.markdown(f"[Source]({recipe['source_url']})")
            st.write("**Have:** " + (", ".join(match["matched_ingredients"]) or "none"))
            st.write("**Missing:** " + (", ".join(match["missing_ingredients"]) or "none"))
            st.write("**Steps:**")
            for i, step in enumerate(recipe["steps"], 1):
                st.write(f"{i}. {step}")

st.header("Ask about your recipes")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # opaque provider history, replayed each turn (API is stateless)
if "chat_display" not in st.session_state:
    st.session_state.chat_display = []  # [(role, text)] for rendering

for role, text in st.session_state.chat_display:
    with st.chat_message(role):
        st.write(text)

if prompt := st.chat_input("e.g. \"I have chicken, rice, and broccoli - what should I make?\""):
    st.session_state.chat_display.append(("user", prompt))
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = client.post(
                    "/chat", json={"message": prompt, "history": st.session_state.chat_history}
                )
                response.raise_for_status()
                body = response.json()
                st.session_state.chat_history = body["history"]
                st.session_state.chat_display.append(("assistant", body["reply"]))
                st.write(body["reply"])
            except httpx.HTTPStatusError as exc:
                st.error(f"Couldn't respond: {_error_detail(exc)}")
            except httpx.HTTPError as exc:
                st.error(f"Request failed: {exc}")

st.header("Your recipes")

# Purely decorative - an unknown cuisine still gets a box, just with the plate.
CUISINE_EMOJI = {
    "italian": "🍝", "mexican": "🌮", "chinese": "🥟", "japanese": "🍣", "korean": "🥘",
    "indian": "🍛", "thai": "🍜", "vietnamese": "🍲", "american": "🍔",
    "mediterranean": "🫒", "french": "🥐", "middle_eastern": "🧆", "other": "🍽️",
}


def _cuisine_label(cuisine: str) -> str:
    return cuisine.replace("_", " ").title()


def _select_cuisine(cuisine: str | None) -> None:
    st.session_state.selected_cuisine = cuisine


if "selected_cuisine" not in st.session_state:
    st.session_state.selected_cuisine = None

filter_cols = st.columns(3)
with filter_cols[0]:
    meal_type_filter = st.selectbox("Meal type", ["Any", *MEAL_TYPES])
with filter_cols[1]:
    max_cook_time_filter = st.number_input(
        "Max cook time (min)", min_value=0, value=0, step=5,
        help="0 means no time limit",
    )
with filter_cols[2]:
    sort_label = st.selectbox("Sort by", ["Newest", "Highest rated"])

# Cuisine is deliberately NOT sent to the API: the boxes need a count for every
# cuisine, so fetch once with the other filters and split by cuisine here.
params = {"sort": "rating" if sort_label == "Highest rated" else "newest"}
if meal_type_filter != "Any":
    params["meal_type"] = meal_type_filter
if max_cook_time_filter:
    params["max_cook_time_minutes"] = int(max_cook_time_filter)

all_recipes = []
try:
    response = client.get("/recipes", params=params)
    response.raise_for_status()
    all_recipes = response.json()
except httpx.HTTPError as exc:
    st.error(f"Couldn't load recipes: {exc}")

counts: dict[str, int] = {}
for r in all_recipes:
    if r.get("cuisine"):
        counts[r["cuisine"]] = counts.get(r["cuisine"], 0) + 1

selected_cuisine = st.session_state.selected_cuisine
if selected_cuisine is not None and selected_cuisine not in counts:
    # Its last recipe was filtered out or re-tagged - fall back to browsing.
    selected_cuisine = st.session_state.selected_cuisine = None

if selected_cuisine is None:
    # Browse by navigating rather than a dropdown: one big box per cuisine that
    # has recipes, in the closed vocabulary's order (ADR-0009).
    present = [c for c in CUISINES if c in counts]
    if present:
        st.markdown(
            "<style>.st-key-cuisine-grid button {min-height: 7rem;}"
            " .st-key-cuisine-grid button [data-testid=stMarkdownContainer]"
            " {display: flex; flex-direction: column; align-items: center;}"
            " .st-key-cuisine-grid button p {margin: 0; font-size: 1.1rem;}"
            " .st-key-cuisine-grid button p:first-child {font-size: 2rem;}</style>",
            unsafe_allow_html=True,
        )
        with st.container(key="cuisine-grid"):
            # Row by row, not one column per third: on a phone the columns stack,
            # and this keeps the boxes in the same order there too.
            for row_start in range(0, len(present), 3):
                row = st.columns(3)
                for col, cuisine in zip(row, present[row_start:row_start + 3]):
                    col.button(
                        # Button labels are markdown; blank lines make separate
                        # paragraphs, which the CSS above sizes individually.
                        f"{CUISINE_EMOJI.get(cuisine, '🍽️')}\n\n**{_cuisine_label(cuisine)}**\n\n"
                        f"{counts[cuisine]} recipe{'s' if counts[cuisine] != 1 else ''}",
                        key=f"cuisine-box-{cuisine}",
                        on_click=_select_cuisine,
                        args=(cuisine,),
                        width="stretch",
                    )
        st.subheader("All recipes")
    recipes = all_recipes
else:
    nav_cols = st.columns([4, 1])
    with nav_cols[0]:
        st.subheader(
            f"{CUISINE_EMOJI.get(selected_cuisine, '🍽️')} {_cuisine_label(selected_cuisine)}"
        )
    with nav_cols[1]:
        st.button("← All cuisines", on_click=_select_cuisine, args=(None,))
    recipes = [r for r in all_recipes if r.get("cuisine") == selected_cuisine]


def _save_rating(recipe_id: int, widget_key: str) -> None:
    # st.feedback("stars") reports 0-4 (or None once un-selected); the API wants 1-5.
    stars = st.session_state[widget_key]
    try:
        client.put(
            f"/recipes/{recipe_id}/rating",
            json={"rating": None if stars is None else stars + 1},
        ).raise_for_status()
    except httpx.HTTPError as exc:
        st.toast(f"Couldn't save rating: {exc}")


has_filters = any(k != "sort" for k in params)
if not recipes:
    st.write("No recipes match those filters." if has_filters else "No recipes yet — add one above.")
for recipe in recipes:
    tags = []
    if recipe.get("cuisine"):
        tags.append(recipe["cuisine"].replace("_", " ").title())
    if recipe.get("meal_type"):
        tags.append(recipe["meal_type"].replace("_", " ").title())
    if recipe.get("cook_time_minutes"):
        tags.append(f"{recipe['cook_time_minutes']} min")
    if recipe.get("rating"):
        tags.append("★" * recipe["rating"])
    label = recipe["title"] + (f"  ·  {' · '.join(tags)}" if tags else "")

    with st.expander(label):
        st.markdown(f"[Source]({recipe['source_url']}) · {recipe['source_platform']}")
        rating_key = f"rating-{recipe['id']}"
        st.caption("Your rating")
        st.feedback(
            "stars",
            key=rating_key,
            default=recipe["rating"] - 1 if recipe.get("rating") else None,
            on_change=_save_rating,
            args=(recipe["id"], rating_key),
        )
        st.write("**Ingredients:**")
        for ingredient in recipe["ingredients"]:
            quantity = f"{ingredient['quantity']} " if ingredient.get("quantity") else ""
            st.write(f"- {quantity}{ingredient['name']}")
        st.write("**Steps:**")
        for i, step in enumerate(recipe["steps"], 1):
            st.write(f"{i}. {step}")

        with st.form(key=f"edit-{recipe['id']}"):
            st.write("**Edit this recipe**")
            edit_title = st.text_input("Title", value=recipe["title"])
            edit_steps_text = st.text_area(
                "Steps (one per line)", value="\n".join(recipe["steps"])
            )
            edit_ingredients_text = st.text_area(
                "Ingredients (one per line, as 'name, quantity')",
                value=_ingredients_to_text(recipe["ingredients"]),
            )

            cuisine_options = ["(none)", *CUISINES]
            edit_cuisine = st.selectbox(
                "Cuisine",
                cuisine_options,
                index=_select_index(cuisine_options, recipe.get("cuisine")),
            )
            meal_type_options = ["(none)", *MEAL_TYPES]
            edit_meal_type = st.selectbox(
                "Meal type",
                meal_type_options,
                index=_select_index(meal_type_options, recipe.get("meal_type")),
            )
            edit_cook_time = st.number_input(
                "Cook time (min, 0 = unknown)",
                min_value=0,
                value=recipe.get("cook_time_minutes") or 0,
            )

            if st.form_submit_button("Save changes"):
                update_payload = {
                    "title": edit_title,
                    "steps": [s.strip() for s in edit_steps_text.splitlines() if s.strip()],
                    "cuisine": edit_cuisine if edit_cuisine != "(none)" else None,
                    "meal_type": edit_meal_type if edit_meal_type != "(none)" else None,
                    "cook_time_minutes": edit_cook_time or None,
                    "ingredients": _parse_ingredients_text(edit_ingredients_text),
                }
                try:
                    put_response = client.put(f"/recipes/{recipe['id']}", json=update_payload)
                    put_response.raise_for_status()
                    st.success("Saved.")
                    st.rerun()
                except httpx.HTTPStatusError as exc:
                    st.error(f"Couldn't save: {_error_detail(exc)}")
                except httpx.HTTPError as exc:
                    st.error(f"Request failed: {exc}")
