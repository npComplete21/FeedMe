"""Pure helpers for the Streamlit UI: no Streamlit import, no I/O.

Kept out of the Streamlit pages so the rules worth testing (what counts as a link,
which platform a URL belongs to, how the recipe search matches, how ingredient
text round-trips) run under plain pytest without a Streamlit runtime. Like
vocabulary.py, this module is deliberately free of backend imports: the UI is a
pure HTTP client of the API (ADR-0004).
"""

import re
from collections import Counter
from typing import Literal
from urllib.parse import urlsplit

Platform = Literal["youtube", "instagram", "website"]

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_YOUTUBE_HOSTS = ("youtube.com", "youtu.be")
_INSTAGRAM_HOSTS = ("instagram.com",)


def normalize_url(raw: str) -> str | None:
    """Trim `raw` and make it a full URL, or return None if it isn't a link.

    A scheme-less paste like "youtu.be/abc" gets `https://` prepended. Anything
    blank, containing inner whitespace, or without a dot-containing host
    ("chicken curry", "hello") is rejected so free text isn't sent for ingestion,
    and so is any scheme other than http/https ("ftp://a.com", "file://x.y/z").
    """
    url = raw.strip()
    if not url or any(ch.isspace() for ch in url):
        return None
    if not _SCHEME_RE.match(url):
        url = f"https://{url}"
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    if not host or "." not in host:
        return None
    return url


def _host_matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith(f".{d}") for d in domains)


def detect_platform(url: str) -> Platform:
    """Classify a URL by hostname, matching on a dot boundary.

    `notyoutube.com` and `youtube.com.evil.io` are websites, not YouTube.
    """
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return "website"
    if _host_matches(host, _YOUTUBE_HOSTS):
        return "youtube"
    if _host_matches(host, _INSTAGRAM_HOSTS):
        return "instagram"
    return "website"


def search_recipes(recipes: list[dict], query: str) -> list[dict]:
    """Case-insensitive substring match over title and ingredient names.

    A blank query returns `recipes` unchanged; order is always preserved.
    """
    needle = query.strip().lower()
    if not needle:
        return recipes
    matches = []
    for recipe in recipes:
        haystack = [recipe.get("title") or "", *(i.get("name") or "" for i in recipe.get("ingredients") or [])]
        if any(needle in text.lower() for text in haystack):
            matches.append(recipe)
    return matches


def cuisine_counts(recipes: list[dict]) -> dict[str, int]:
    """Recipe count per cuisine, ignoring recipes with no cuisine."""
    return dict(Counter(r["cuisine"] for r in recipes if r.get("cuisine")))


def cuisine_label(cuisine: str) -> str:
    """Human label for a stored value: "middle_eastern" -> "Middle Eastern"."""
    return cuisine.replace("_", " ").title()


def recipe_tags(recipe: dict) -> list[str]:
    """Display tags in fixed order: cuisine, meal type, cook time, rating stars.

    Each is included only if the recipe has it.
    """
    tags = []
    if recipe.get("cuisine"):
        tags.append(cuisine_label(recipe["cuisine"]))
    if recipe.get("meal_type"):
        tags.append(cuisine_label(recipe["meal_type"]))
    if recipe.get("cook_time_minutes"):
        tags.append(f"{recipe['cook_time_minutes']} min")
    if recipe.get("rating"):
        tags.append("★" * recipe["rating"])
    return tags


def ingredients_to_text(ingredients: list[dict]) -> str:
    """One ingredient per line: "name, quantity", or just "name" without a quantity."""
    lines = []
    for ing in ingredients:
        lines.append(f"{ing['name']}, {ing['quantity']}" if ing.get("quantity") else ing["name"])
    return "\n".join(lines)


def parse_ingredients_text(text: str) -> list[dict]:
    """Inverse of ingredients_to_text; blank lines are skipped."""
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


def parse_pantry(text: str) -> list[str]:
    """Split comma-separated pantry input, stripping whitespace and dropping empties."""
    return [item.strip() for item in text.split(",") if item.strip()]
