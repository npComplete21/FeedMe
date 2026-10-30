"""FeedMe UI entry point: the app shell around the pages in app/ui/views/.

The folder is deliberately not called `pages/`: a `pages/` folder next to this
file switches on Streamlit's legacy folder-based navigation (a sidebar listing
every file, each reachable by URL without going through this entry file) on
any run that hasn't called st.navigation yet.

Each run: page config, register the pages (Streamlit's own nav hidden), the
login gate, then the shell (CSS, header, bottom tab bar) and the current page.
The UI is a thin HTTP client of the API (ADR-0004).
"""

import streamlit as st

from app.ui import auth, nav

st.set_page_config(
    page_title="FeedMe",
    page_icon="🍳",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Registered before the login gate, not after it, so a deep link (e.g.
# /recipe?recipe=12) that hits the login screen is still the current page after
# logging in, instead of a "page not found".
page = st.navigation(
    [
        st.Page("views/recipes.py", title="Recipes", icon=":material/menu_book:", default=True),
        st.Page("views/pantry.py", title="Pantry", icon=":material/kitchen:"),
        st.Page("views/save.py", title="Save", icon=":material/add:"),
        st.Page("views/ask.py", title="Ask", icon=":material/chat:"),
        st.Page("views/recipe.py", title="Recipe", url_path="recipe"),
    ],
    position="hidden",
)

auth.require_login()

nav.inject_css()
nav.render_header()
nav.render_tab_bar()
page.run()
