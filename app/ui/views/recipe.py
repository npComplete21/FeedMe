"""Recipe page: read a recipe, rate it, edit it.

Which recipe is decided each run: `?recipe=<id>` in the URL first (that is what
survives a browser refresh and what a shared link carries), else the id
`nav.open_recipe` left in session state. Whichever won is written back to the
URL, so the address always names the recipe on screen. A missing, non-numeric or
unknown id shows "Recipe not found" with a way back, never a traceback.

There is no single-recipe endpoint, so the recipe is found in `GET /recipes`.
Editing is behind an Edit button; the flag is keyed per recipe id so opening
another recipe doesn't inherit edit mode, and `nav.open_recipe` drops it so
reopening a recipe left mid-edit starts in read mode. Save is a full-replace PUT
(ADR-0010). The back link returns to the list the user came from
(`recipe_back_to`, set by `nav.open_recipe`), Recipes by default.
"""

import httpx
import streamlit as st

from app.ui import api, components, logic, nav
from app.ui.vocabulary import CUISINES, MEAL_TYPES

PLATFORM_LABELS = {"youtube": "YouTube", "instagram": "Instagram", "website": "the website"}
NONE_OPTION = "(none)"


def _resolve_recipe_id() -> int | None:
    """The id to show, or None if there isn't a usable one."""
    raw = st.query_params.get("recipe")
    if raw is None:
        raw = st.session_state.get("open_recipe_id")
        if raw is not None:
            st.query_params["recipe"] = str(raw)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _select_index(options: list[str], current: str | None) -> int:
    return options.index(current) if current in options else 0


def _back_link() -> None:
    # Back to the list the user came from (nav.open_recipe records it); Recipes
    # when nothing was recorded, e.g. after a refresh or from a shared link.
    page, label = st.session_state.get("recipe_back_to", nav.BACK_TO_RECIPES)
    st.page_link(page, label=label)


def _not_found() -> None:
    _back_link()
    st.info("Recipe not found.")
    st.stop()


def _save_rating(recipe_id: int, widget_key: str) -> None:
    # st.feedback("stars") reports 0-4 (None once un-selected); the API wants 1-5,
    # and null to clear the rating.
    stars = st.session_state[widget_key]
    try:
        api.get_client().put(
            f"/recipes/{recipe_id}/rating",
            json={"rating": None if stars is None else stars + 1},
        ).raise_for_status()
    except httpx.HTTPError as exc:
        st.toast(f"Couldn't save rating: {exc}")


def _start_editing(flag: str) -> None:
    st.session_state[flag] = True


def _read_view(recipe: dict, edit_flag: str) -> None:
    rid = recipe["id"]
    st.subheader(components.md_escape(recipe["title"]))
    tags = " · ".join(logic.recipe_tags(recipe))
    if tags:
        st.caption(tags)

    rating_key = f"rating-{rid}"
    st.caption("Your rating")
    st.feedback(
        "stars",
        key=rating_key,
        default=recipe["rating"] - 1 if recipe.get("rating") else None,
        on_change=_save_rating,
        args=(rid, rating_key),
    )

    source_url = recipe.get("source_url") or ""
    if source_url.startswith(("http://", "https://")):
        label = PLATFORM_LABELS.get(recipe.get("source_platform"), "the source")
        st.link_button(f"Open on {label}", source_url, icon=":material/open_in_new:")

    st.markdown("**Ingredients**")
    st.markdown(
        "\n".join(
            "- "
            + (f"{components.md_escape(i['quantity'])} " if i.get("quantity") else "")
            + components.md_escape(i["name"])
            for i in recipe["ingredients"]
        )
        or "_None listed_"
    )
    st.markdown("**Steps**")
    st.markdown(
        "\n".join(f"{n}. {components.md_escape(step)}" for n, step in enumerate(recipe["steps"], 1))
        or "_None listed_"
    )

    st.button(
        "Edit",
        key=f"edit-{rid}",
        icon=":material/edit:",
        on_click=_start_editing,
        args=(edit_flag,),
        width="stretch",
    )


def _edit_view(recipe: dict, edit_flag: str) -> None:
    rid = recipe["id"]
    st.subheader("Edit recipe")
    with st.form(f"edit-form-{rid}"):
        title = st.text_input("Title", value=recipe["title"])
        steps_text = st.text_area("Steps (one per line)", value="\n".join(recipe["steps"]))
        ingredients_text = st.text_area(
            "Ingredients (one per line, as 'name, quantity')",
            value=logic.ingredients_to_text(recipe["ingredients"]),
        )
        cuisine_options = [NONE_OPTION, *CUISINES]
        cuisine = st.selectbox(
            "Cuisine",
            cuisine_options,
            index=_select_index(cuisine_options, recipe.get("cuisine")),
        )
        meal_type_options = [NONE_OPTION, *MEAL_TYPES]
        meal_type = st.selectbox(
            "Meal type",
            meal_type_options,
            index=_select_index(meal_type_options, recipe.get("meal_type")),
        )
        cook_time = st.number_input(
            "Cook time (min, 0 = unknown)",
            min_value=0,
            value=recipe.get("cook_time_minutes") or 0,
        )
        save = st.form_submit_button(
            "Save", key=f"edit-save-{rid}", type="primary", width="stretch"
        )
        cancel = st.form_submit_button("Cancel", key=f"edit-cancel-{rid}", width="stretch")

    if cancel:
        st.session_state[edit_flag] = False
        st.rerun()
    if save:
        payload = {
            "title": title,
            "steps": [s.strip() for s in steps_text.splitlines() if s.strip()],
            "cuisine": cuisine if cuisine != NONE_OPTION else None,
            "meal_type": meal_type if meal_type != NONE_OPTION else None,
            "cook_time_minutes": cook_time or None,
            "ingredients": logic.parse_ingredients_text(ingredients_text),
        }
        try:
            api.get_client().put(f"/recipes/{rid}", json=payload).raise_for_status()
        except httpx.HTTPStatusError as exc:
            st.error(f"Couldn't save: {api.error_detail(exc)}")
        except httpx.HTTPError as exc:
            st.error(f"Request failed: {exc}")
        else:
            st.session_state[edit_flag] = False
            st.toast("Saved")
            st.rerun()


recipe_id = _resolve_recipe_id()
if recipe_id is None:
    _not_found()

try:
    response = api.get_client().get("/recipes")
    response.raise_for_status()
    recipe = next((r for r in response.json() if r["id"] == recipe_id), None)
except httpx.HTTPError as exc:
    _back_link()
    st.error(f"Couldn't load the recipe: {exc}")
    st.stop()

if recipe is None:
    _not_found()

edit_flag = f"editing-{recipe_id}"
if st.session_state.get(edit_flag):
    _edit_view(recipe, edit_flag)
else:
    _back_link()
    _read_view(recipe, edit_flag)
