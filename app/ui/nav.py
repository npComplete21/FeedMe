"""The app shell around every page: header, bottom tab bar, mobile CSS.

Streamlit's own navigation is hidden (`st.navigation(..., position="hidden")`)
and replaced by a phone-style bar of `st.page_link`s in a keyed container, which
the CSS below pins to the bottom of the screen (the same `.st-key-<name>`
technique the cuisine grid uses).
"""

import streamlit as st

from app.ui import auth

# (page file relative to the entry file, label, icon), left to right. The Save
# tab sits in the centre and is the emphasised one (see `.st-key-tab-save`).
TABS = [
    ("views/recipes.py", "Recipes", ":material/menu_book:"),
    ("views/pantry.py", "Pantry", ":material/kitchen:"),
    ("views/save.py", "Save", ":material/add:"),
    ("views/ask.py", "Ask", ":material/chat:"),
]
SAVE_PAGE = "views/save.py"

_LIGHT = {"bg": "#ffffff", "border": "rgba(49, 51, 63, 0.15)"}
_DARK = {"bg": "#0e1117", "border": "rgba(250, 250, 250, 0.15)"}

_CSS = """
<style>
/* Streamlit's own chrome (toolbar, deploy button, running indicator). */
header[data-testid="stHeader"] {{ display: none; }}

/* The tab bar's height - a floor it is guaranteed to reach (see .st-key-tab-bar
   below), so everything that must clear the bar can be sized from one value. */
:root {{
  --feedme-tab-bar-h: calc(3.25rem + env(safe-area-inset-bottom));
}}

/* Room at the bottom so the fixed tab bar never covers the last item. */
[data-testid="stMainBlockContainer"] {{
  padding: 0.75rem 1rem calc(var(--feedme-tab-bar-h) + 2.25rem);
}}

/* Ask tab: Streamlit pins st.chat_input to the bottom of the viewport inside
   `stBottom` > `stBottomBlockContainer`. Its own bottom padding is a fixed 3.5rem
   that knows nothing about our bar, so the input only cleared the bar by luck
   (and would slide under it on a phone with a home-indicator inset). Pad it by
   the bar's height instead. NOTE: `stBottomBlockContainer` is a Streamlit
   internal test id, not a public API - re-check this rule on Streamlit upgrades. */
[data-testid="stBottomBlockContainer"] {{
  padding-bottom: calc(var(--feedme-tab-bar-h) + 0.5rem);
}}

/* Comfortable tap targets. */
.stButton button, .stFormSubmitButton button, [data-testid="stPopover"] button {{
  min-height: 2.75rem;
}}

/* Recipe rows (components.recipe_row): left-aligned title, muted tag line. */
[class*="st-key-recipe-row-"] button {{
  justify-content: flex-start;
  text-align: left;
  height: auto;
  padding: 0.6rem 0.9rem;
}}
[class*="st-key-recipe-row-"] button > div,
[class*="st-key-recipe-row-"] button > div > span {{
  width: 100%;
  justify-content: flex-start;
}}
[class*="st-key-recipe-row-"] button [data-testid="stMarkdownContainer"] {{
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
}}
[class*="st-key-recipe-row-"] button p {{ margin: 0; }}
[class*="st-key-recipe-row-"] button p + p {{ font-size: 0.85rem; opacity: 0.7; }}

/* Header: app name left, account control right. */
.st-key-app-header [data-testid="stMarkdown"] p {{
  margin: 0; font-size: 1.25rem; font-weight: 700;
}}

/* The bottom tab bar. */
.st-key-tab-bar {{
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  box-sizing: border-box;
  min-height: var(--feedme-tab-bar-h);
  background: {bg};
  border-top: 1px solid {border};
  padding: 0.25rem 0.5rem calc(0.25rem + env(safe-area-inset-bottom));
  justify-content: space-around;
  flex-wrap: nowrap;
  gap: 0;
}}
.st-key-tab-bar > div {{ flex: 1 1 0; min-width: 0; max-width: 8rem; }}
.st-key-tab-bar [data-testid="stPageLink"] {{ width: 100%; }}
.st-key-tab-bar [data-testid="stPageLink-NavLink"] {{
  flex-direction: column;
  justify-content: center;
  gap: 0.1rem;
  width: 100%;
  min-height: 3.25rem;
  margin: 0;
  padding: 0.25rem;
  border-radius: 0.75rem;
}}
.st-key-tab-bar [data-testid="stPageLink-NavLink"] p {{ font-size: 0.75rem; }}
.st-key-tab-bar [data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] {{
  font-size: 1.5rem;
}}

/* The centre ＋ Save tab: its own keyed wrapper would otherwise shrink to fit,
   and the icon sits in a filled circle. */
.st-key-tab-save, .st-key-tab-save [data-testid="stElementContainer"] {{ width: 100%; }}
.st-key-tab-save [data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] {{
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  background: #ff4b4b;
  color: #ffffff;
  font-size: 1.5rem;
}}
</style>
"""


def inject_css() -> None:
    colors = _DARK if st.context.theme.type == "dark" else _LIGHT
    st.markdown(_CSS.format(**colors), unsafe_allow_html=True)


def render_header() -> None:
    with st.container(
        key="app-header",
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
    ):
        st.markdown("🍳 FeedMe")
        with st.popover("Account", icon=":material/account_circle:", type="tertiary"):
            # Code span, not the raw address - otherwise Streamlit's markdown
            # renderer autolinks the email into a clickable mailto: link.
            st.caption(f"Logged in as `{st.session_state.user_email}`")
            st.button(
                "Log out", icon=":material/logout:", on_click=auth.log_out, width="stretch"
            )


def render_tab_bar() -> None:
    with st.container(key="tab-bar", horizontal=True):
        for page, label, icon in TABS:
            if page == SAVE_PAGE:
                with st.container(key="tab-save"):
                    st.page_link(page, label=label, icon=icon)
            else:
                st.page_link(page, label=label, icon=icon)


def open_recipe(recipe_id: int) -> None:
    """Go to the recipe page for `recipe_id`.

    The id goes in session state for the page to read, and in the URL as
    `?recipe=<id>` so a refresh or a shared link reopens the same recipe -
    `st.switch_page` clears every query param it isn't given.

    Call it from the script body (`if st.button(...): nav.open_recipe(id)`),
    never as a widget's `on_click`: inside a callback Streamlit turns the page
    switch into a no-op ("Calling st.rerun() within a callback is a no-op"),
    so only the query param would change.
    """
    st.session_state.open_recipe_id = recipe_id
    st.switch_page("views/recipe.py", query_params={"recipe": str(recipe_id)})
