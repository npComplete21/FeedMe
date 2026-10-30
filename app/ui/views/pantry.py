"""Pantry tab: "I have X, Y, Z" -> recipes ranked by how much of them you can make.

POSTs `/match` with the parsed ingredient list. Each result shows the title, the
match percentage, what you Have and what is Missing, and an Open recipe button;
the steps and source live on the recipe page, not here.

Session keys, both plain so they outlive the widget: `pantry_text` (the field
contents) and `pantry_results` ({pantry, matches} of the last successful
search, None before the first). The text field has its own `pantry_text_widget`
key and the plain key mirrors it, because Streamlit forgets a widget's state on
any run where the widget isn't drawn (e.g. while another tab or the recipe page
is showing). Keeping the results here is what lets the page re-render them on
the way back without asking the API again.
"""

import httpx
import streamlit as st

from app.ui import api, components, logic, nav

BLANK_PROMPT = "Type what you have, separated by commas"


def _search(pantry: list[str]) -> None:
    """Run the match and store the results; report a failure inline.

    A failed request leaves the previous results in place.
    """
    try:
        response = api.get_client().post("/match", json={"pantry": pantry})
        response.raise_for_status()
        matches = response.json()
    except httpx.HTTPStatusError as exc:
        st.error(components.md_escape(api.error_detail(exc)))
        return
    except httpx.HTTPError as exc:
        st.error(components.md_escape(f"Request failed: {exc}"))
        return
    st.session_state.pantry_results = {"pantry": pantry, "matches": matches}


def _names(names: list[str]) -> str:
    return ", ".join(components.md_escape(n) for n in names) or "none"


def _result(match: dict) -> None:
    recipe = match["recipe"]
    with st.container(border=True):
        st.markdown(f"**{components.md_escape(recipe['title'])}** — {match['match_ratio']:.0%} match")
        st.markdown(f"**Have:** {_names(match['matched_ingredients'])}")
        st.markdown(f"**Missing:** {_names(match['missing_ingredients'])}")
        # A button handled in the script body, not an on_click: inside a
        # callback Streamlit turns the page switch into a no-op (see
        # nav.open_recipe).
        if st.button("Open recipe", key=f"pantry-open-{recipe['id']}", width="stretch"):
            nav.open_recipe(recipe["id"])


st.session_state.setdefault("pantry_results", None)

st.subheader("What can I make?")
pantry_text = st.text_input(
    "What's in your kitchen? (comma-separated)",
    value=st.session_state.get("pantry_text", ""),
    key="pantry_text_widget",
    placeholder="eggs, pasta, garlic",
)
st.session_state.pantry_text = pantry_text

if st.button("Find recipes", key="pantry-find", type="primary", width="stretch"):
    pantry = logic.parse_pantry(pantry_text)
    if pantry:
        _search(pantry)
    else:
        st.info(BLANK_PROMPT)

results = st.session_state.pantry_results
if results is not None:
    if results["matches"]:
        for match in results["matches"]:
            _result(match)
    else:
        st.write("No matches.")
