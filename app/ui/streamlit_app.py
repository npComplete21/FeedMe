import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.environ.get("FEEDME_API_URL", "http://localhost:8000")

# Kept in sync by hand with Cuisine/MealType in app/parsing/recipe_parser.py.
# Not imported directly - the UI is a pure HTTP client of the API (ADR-0004),
# and importing backend code here would drag anthropic/sqlalchemy/etc. into
# the UI's Docker image once Phase 2 splits them apart.
CUISINES = [
    "italian", "mexican", "chinese", "japanese", "korean", "indian", "thai",
    "vietnamese", "american", "mediterranean", "french", "middle_eastern", "other",
]
MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack", "dessert", "drink", "appetizer"]

st.set_page_config(page_title="FeedMe", page_icon="🍳")
st.title("FeedMe")

client = httpx.Client(base_url=API_BASE_URL, timeout=60.0)


def _error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        return exc.response.json().get("detail", exc.response.text)
    except ValueError:
        return exc.response.text


st.header("Add a recipe")
source_platform = st.radio("Source", ["youtube", "instagram"], horizontal=True)
url = st.text_input("URL")
caption_text = None
if source_platform == "instagram":
    caption_text = st.text_area("Paste the caption text")

if st.button("Ingest recipe"):
    if not url:
        st.error("URL is required")
    elif source_platform == "instagram" and not caption_text:
        st.error("Caption text is required for Instagram")
    else:
        payload = {"source_platform": source_platform, "url": url}
        if caption_text:
            payload["caption_text"] = caption_text
        with st.spinner("Parsing recipe..."):
            try:
                response = client.post("/recipes/ingest", json=payload)
                response.raise_for_status()
                st.success(f"Added: {response.json()['title']}")
            except httpx.HTTPStatusError as exc:
                st.error(f"Couldn't parse this recipe: {_error_detail(exc)}")
            except httpx.HTTPError as exc:
                st.error(f"Request failed: {exc}")

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

st.header("Your recipes")

filter_cols = st.columns(3)
with filter_cols[0]:
    cuisine_filter = st.selectbox("Cuisine", ["Any", *CUISINES])
with filter_cols[1]:
    meal_type_filter = st.selectbox("Meal type", ["Any", *MEAL_TYPES])
with filter_cols[2]:
    max_cook_time_filter = st.number_input(
        "Max cook time (min)", min_value=0, value=0, step=5,
        help="0 means no time limit",
    )

params = {}
if cuisine_filter != "Any":
    params["cuisine"] = cuisine_filter
if meal_type_filter != "Any":
    params["meal_type"] = meal_type_filter
if max_cook_time_filter:
    params["max_cook_time_minutes"] = int(max_cook_time_filter)

recipes = []
try:
    response = client.get("/recipes", params=params)
    response.raise_for_status()
    recipes = response.json()
except httpx.HTTPError as exc:
    st.error(f"Couldn't load recipes: {exc}")

if not recipes:
    st.write("No recipes match those filters." if params else "No recipes yet — add one above.")
for recipe in recipes:
    tags = []
    if recipe.get("cuisine"):
        tags.append(recipe["cuisine"].replace("_", " ").title())
    if recipe.get("meal_type"):
        tags.append(recipe["meal_type"].replace("_", " ").title())
    if recipe.get("cook_time_minutes"):
        tags.append(f"{recipe['cook_time_minutes']} min")
    label = recipe["title"] + (f"  ·  {' · '.join(tags)}" if tags else "")

    with st.expander(label):
        st.markdown(f"[Source]({recipe['source_url']}) · {recipe['source_platform']}")
        st.write("**Ingredients:**")
        for ingredient in recipe["ingredients"]:
            quantity = f"{ingredient['quantity']} " if ingredient.get("quantity") else ""
            st.write(f"- {quantity}{ingredient['name']}")
        st.write("**Steps:**")
        for i, step in enumerate(recipe["steps"], 1):
            st.write(f"{i}. {step}")
