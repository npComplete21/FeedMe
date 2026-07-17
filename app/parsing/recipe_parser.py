from __future__ import annotations

import os
from typing import Literal

import anthropic
from pydantic import BaseModel

DEFAULT_MODEL = "claude-opus-4-8"
MODEL = os.environ.get("RECIPE_PARSER_MODEL", DEFAULT_MODEL)

_SYSTEM_PROMPT = (
    "You extract structured recipes from raw social media captions or video "
    "transcripts. Only use information present in the text - do not invent "
    "ingredients, quantities, or steps that aren't there. If a quantity isn't "
    "stated for an ingredient, omit it rather than guessing. Likewise, only set "
    "cuisine, meal_type, or cook_time_minutes when the text actually supports "
    "it - leave them null rather than guessing. Pick the single closest cuisine "
    "from the allowed list; use 'other' if none fit well."
)

Cuisine = Literal[
    "italian",
    "mexican",
    "chinese",
    "japanese",
    "korean",
    "indian",
    "thai",
    "vietnamese",
    "american",
    "mediterranean",
    "french",
    "middle_eastern",
    "other",
]

MealType = Literal[
    "breakfast",
    "lunch",
    "dinner",
    "snack",
    "dessert",
    "drink",
    "appetizer",
]


class ParsedIngredient(BaseModel):
    name: str
    quantity: str | None = None
    raw_text: str


class ParsedRecipe(BaseModel):
    title: str
    ingredients: list[ParsedIngredient]
    steps: list[str]
    cuisine: Cuisine | None = None
    meal_type: MealType | None = None
    cook_time_minutes: int | None = None


class RecipeParseError(Exception):
    """Raised when the model declines or otherwise fails to produce a structured recipe."""


def parse_recipe(raw_text: str, *, client: anthropic.Anthropic | None = None) -> ParsedRecipe:
    client = client or anthropic.Anthropic()

    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": raw_text}],
        output_format=ParsedRecipe,
    )

    if response.stop_reason == "refusal":
        raise RecipeParseError("Model declined to parse this content")

    return response.parsed_output
