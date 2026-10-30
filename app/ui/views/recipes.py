"""Recipes tab: search bar on top, cuisine boxes below it, recipe lists.

Three states, picked each run from the search box and `selected_cuisine`:

- blank search, nothing selected: the cuisine boxes (2 per row) plus an
  "All recipes" box, so a recipe with no cuisine stays reachable;
- blank search, a box tapped: that cuisine's list (or everything), with Back;
- anything typed: matching recipes from the whole library, boxes hidden.

Session keys: `selected_cuisine` (None = boxes, "__all__" = everything),
`recipes_sort` ("rating" | "newest") and `recipes_query`. The widgets have their
own `*_widget` keys and these plain keys mirror them, because Streamlit forgets
a widget's state on any run where the widget isn't drawn (e.g. the Sort control
while the boxes are showing) and the choice has to outlive that.
"""

import httpx
import streamlit as st

from app.ui import api, components, logic
from app.ui.vocabulary import CUISINES

ALL = "__all__"
SORT_LABELS = {"rating": "Highest rated", "newest": "Newest"}

# Purely decorative - an unknown cuisine still gets a box, just with the plate.
CUISINE_EMOJI = {
    "italian": "🍝", "mexican": "🌮", "chinese": "🥟", "japanese": "🍣", "korean": "🥘",
    "indian": "🍛", "thai": "🍜", "vietnamese": "🍲", "american": "🍔",
    "mediterranean": "🫒", "french": "🥐", "middle_eastern": "🧆", "other": "🍽️",
}
ALL_EMOJI = "📖"

# Boxes are buttons whose label is markdown: blank lines make separate
# paragraphs, which this sizes individually (emoji big, name, count). The grid is
# a wrapping flex row rather than st.columns, because columns stack to one per
# row on a phone and the boxes should stay 2-up.
_CSS = """
<style>
.st-key-cuisine-grid { gap: 0.75rem; }
.st-key-cuisine-grid > div { flex: 0 0 calc(50% - 0.375rem); min-width: 0; }
.st-key-cuisine-grid button { min-height: 7rem; }
.st-key-cuisine-grid button [data-testid=stMarkdownContainer] {
  display: flex; flex-direction: column; align-items: center;
}
.st-key-cuisine-grid button p { margin: 0; font-size: 1rem; }
.st-key-cuisine-grid button p:first-child { font-size: 2rem; }
.st-key-cuisine-grid .st-key-cuisine-box-all { flex-basis: 100%; }
.st-key-cuisine-grid .st-key-cuisine-box-all button { min-height: 3.5rem; }
.st-key-cuisine-grid .st-key-cuisine-box-all button [data-testid=stMarkdownContainer] {
  flex-direction: row; justify-content: center; gap: 0.5rem;
}
.st-key-cuisine-grid .st-key-cuisine-box-all button p:first-child { font-size: 1.5rem; }
</style>
"""


def _select(value: str | None) -> None:
    st.session_state.selected_cuisine = value


def _plural(n: int) -> str:
    return f"{n} recipe{'s' if n != 1 else ''}"


def _cuisine_boxes(recipes: list[dict]) -> None:
    counts = logic.cuisine_counts(recipes)
    st.markdown(_CSS, unsafe_allow_html=True)
    with st.container(key="cuisine-grid", horizontal=True):
        # Closed-vocabulary order (ADR-0009), only cuisines that have recipes.
        for cuisine in (c for c in CUISINES if c in counts):
            st.button(
                f"{CUISINE_EMOJI.get(cuisine, '🍽️')}\n\n**{logic.cuisine_label(cuisine)}**\n\n"
                f"{_plural(counts[cuisine])}",
                key=f"cuisine-box-{cuisine}",
                on_click=_select,
                args=(cuisine,),
                width="stretch",
            )
        # Last, and always: it is the only way to a recipe with no cuisine.
        st.button(
            f"{ALL_EMOJI}\n\n**All recipes · {len(recipes)}**",
            key="cuisine-box-all",
            on_click=_select,
            args=(ALL,),
            width="stretch",
        )


def _sort_control() -> None:
    if "recipes_sort_widget" not in st.session_state:
        st.session_state.recipes_sort_widget = st.session_state.get("recipes_sort", "rating")
    st.session_state.recipes_sort = st.selectbox(
        "Sort by",
        options=list(SORT_LABELS),
        format_func=SORT_LABELS.get,
        key="recipes_sort_widget",
    )


def _rows(recipes: list[dict], key_prefix: str) -> None:
    for recipe in recipes:
        components.recipe_row(recipe, key_prefix)


st.session_state.setdefault("selected_cuisine", None)
st.session_state.setdefault("recipes_sort", "rating")
if "recipes_query_widget" not in st.session_state:
    st.session_state.recipes_query_widget = st.session_state.get("recipes_query", "")

query = st.text_input(
    "Search recipes",
    key="recipes_query_widget",
    placeholder="Search recipes or ingredients",
    icon=":material/search:",
    label_visibility="collapsed",
)
st.session_state.recipes_query = query
searching = bool(query.strip())
selected = st.session_state.selected_cuisine

in_list = searching or selected is not None
if in_list:
    if not searching:
        st.button("← Back", key="recipes-back", on_click=_select, args=(None,), type="tertiary")
        st.subheader(
            "All recipes"
            if selected == ALL
            else f"{CUISINE_EMOJI.get(selected, '🍽️')} {logic.cuisine_label(selected)}"
        )
    _sort_control()

# Cuisine is deliberately NOT sent to the API: the boxes need a count for every
# cuisine, so fetch the whole library once and split it by cuisine here.
try:
    response = api.get_client().get("/recipes", params={"sort": st.session_state.recipes_sort})
    response.raise_for_status()
    all_recipes = response.json()
except httpx.HTTPError as exc:
    st.error(f"Couldn't load recipes: {exc}")
    st.stop()

if not all_recipes:
    st.info("No recipes yet — tap ＋ to save your first one")
    st.stop()

if selected not in (None, ALL) and selected not in logic.cuisine_counts(all_recipes):
    # Its last recipe was deleted or re-tagged elsewhere - fall back to the boxes.
    st.session_state.selected_cuisine = None
    st.rerun()

if searching:
    results = logic.search_recipes(all_recipes, query)
    if results:
        st.caption(_plural(len(results)))
        _rows(results, "search")
    else:
        st.info(f"No recipes match “{query.strip()}”")
elif selected is None:
    _cuisine_boxes(all_recipes)
else:
    shown = (
        all_recipes
        if selected == ALL
        else [r for r in all_recipes if r.get("cuisine") == selected]
    )
    _rows(shown, "list")
