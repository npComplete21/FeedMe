"""Small UI pieces shared by more than one page."""

import re

import streamlit as st

from app.ui import logic, nav

# Characters that would turn part of a title into markdown (bold, italics,
# strike-through, links, LaTeX) inside a button label.
_MD_SPECIALS = re.compile(r"([\\`*_{}\[\]()#+!~|<>$])")


def md_escape(text: str) -> str:
    return _MD_SPECIALS.sub(r"\\\1", text)


def recipe_row(recipe: dict, key_prefix: str) -> None:
    """One full-width tappable row: the title, then a line of tags.

    Tapping it opens the recipe page. The key is `recipe-row-<key_prefix>-<id>`,
    so the same recipe can appear in two lists on one page as long as their
    prefixes differ; the shared `recipe-row-` stem is what the CSS in `nav`
    styles.

    `nav.open_recipe` is called from the script body, not from `on_click`:
    inside a callback Streamlit turns the page switch into a no-op.
    """
    label = f"**{md_escape(recipe['title'])}**"
    tags = " · ".join(logic.recipe_tags(recipe))
    if tags:
        label += f"\n\n{tags}"
    if st.button(label, key=f"recipe-row-{key_prefix}-{recipe['id']}", width="stretch"):
        nav.open_recipe(recipe["id"])
