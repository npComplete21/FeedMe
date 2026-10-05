from __future__ import annotations

import os
from dataclasses import dataclass

import anthropic
from anthropic import beta_tool
from sqlalchemy import select
from sqlalchemy.orm import Session

from typing import get_args

from app.matching.ingredient_matcher import MatchableIngredient, MatchableRecipe, match_recipes
from app.models import Recipe
from app.parsing.recipe_parser import Cuisine
from app.persistence.recipe_queries import find_recipes

DEFAULT_MODEL = "claude-opus-4-8"
MODEL = os.environ.get("RECIPE_CHAT_MODEL", DEFAULT_MODEL)

# Enough for "my top 5/10"; keeps a runaway request from dumping every recipe.
MAX_TOP_RATED = 20

# Caps the tool-call loop so a pathological back-and-forth can't run away -
# a handful of match_pantry calls is the most a real conversation turn needs.
MAX_TOOL_ITERATIONS = 8

_SYSTEM_PROMPT = (
    "You are a cooking assistant answering questions about the user's saved recipe "
    "collection. When the user mentions ingredients they have on hand, call the "
    "match_pantry tool to see which of their saved recipes they can make - never "
    "invent or recall a recipe that the tool didn't return. When recommending a "
    "recipe, cite the match ratio and missing ingredients from the tool's output. "
    "When the user asks for their best, favourite or top-rated recipes, call the "
    "top_rated_recipes tool - their ratings are 1-5 stars they gave themselves - "
    "and say plainly when the matching recipes haven't been rated yet."
)


class RecipeChatError(Exception):
    """Raised when the model declines to respond."""


@dataclass
class ChatReply:
    reply: str
    messages: list[dict]


def chat_about_recipes(
    db: Session,
    user_id: int,
    message: str,
    history: list[dict] | None = None,
    *,
    client: anthropic.Anthropic | None = None,
) -> ChatReply:
    client = client or anthropic.Anthropic()

    @beta_tool
    def match_pantry(pantry: list[str]) -> str:
        """Check which of the user's saved recipes can be made from ingredients they have.

        Args:
            pantry: Ingredient names the user says they have on hand.
        """
        recipes = db.scalars(select(Recipe).where(Recipe.user_id == user_id)).all()
        matchable = [
            MatchableRecipe(
                id=r.id,
                title=r.title,
                ingredients=[MatchableIngredient(name=ri.ingredient.name) for ri in r.ingredients],
            )
            for r in recipes
        ]
        if not matchable:
            return "The user has no saved recipes yet."

        matches = match_recipes(pantry, matchable)
        return "\n".join(
            f"{m.recipe.title} (id={m.recipe.id}): {m.match_ratio:.0%} match. "
            f"Have: {', '.join(m.matched_ingredients) or 'none'}. "
            f"Missing: {', '.join(m.missing_ingredients) or 'none'}."
            for m in matches
        )

    @beta_tool
    def top_rated_recipes(
        ingredient: str | None = None, cuisine: str | None = None, limit: int = 5
    ) -> str:
        """List the user's saved recipes ranked by their own 1-5 star rating, best first.

        Args:
            ingredient: Only recipes that use this ingredient, e.g. "chicken". Omit for any.
            cuisine: Only recipes of this cuisine, e.g. "korean". Omit for any.
            limit: How many recipes to return, at most 20.
        """
        allowed_cuisines = get_args(Cuisine)
        if cuisine is not None:
            cuisine = cuisine.strip().lower().replace(" ", "_")
            if cuisine not in allowed_cuisines:
                return f"Unknown cuisine. Use one of: {', '.join(allowed_cuisines)}."

        recipes = find_recipes(
            db,
            user_id,
            ingredient=ingredient,
            cuisine=cuisine,
            sort="rating",
            limit=max(1, min(limit, MAX_TOP_RATED)),
        )
        if not recipes:
            return "No saved recipes match those filters."

        lines = [
            f"{r.title} (id={r.id}): "
            + (f"rated {r.rating}/5" if r.rating else "unrated")
            + (f", {r.cuisine.replace('_', ' ')}" if r.cuisine else "")
            + f". Ingredients: {', '.join(ri.ingredient.name for ri in r.ingredients) or 'none'}."
            for r in recipes
        ]
        if all(r.rating is None for r in recipes):
            lines.append("None of these recipes have been rated yet.")
        return "\n".join(lines)

    messages: list[dict] = [*(history or []), {"role": "user", "content": message}]

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        tools=[match_pantry, top_rated_recipes],
        messages=messages,
        max_iterations=MAX_TOOL_ITERATIONS,
    )

    last = None
    for response in runner:
        last = response
        # tool_runner uses client.beta.messages.parse() internally, so text blocks
        # come back as ParsedBetaTextBlock with an extra parsed_output field that
        # the API rejects ("Extra inputs are not permitted") if echoed back as-is
        # on the next turn - drop it when mirroring history for the client.
        content = [b.model_dump(exclude={"parsed_output"}) for b in response.content]
        messages.append({"role": "assistant", "content": content})
        tool_response = runner.generate_tool_call_response()
        if tool_response is not None:
            messages.append(tool_response)

    if last is None:
        raise RecipeChatError("Model returned no response")
    if last.stop_reason == "refusal":
        raise RecipeChatError("Model declined to respond")

    reply_text = "".join(b.text for b in last.content if b.type == "text")
    return ChatReply(reply=reply_text, messages=messages)
