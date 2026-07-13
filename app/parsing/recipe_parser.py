from __future__ import annotations

import os

import anthropic
from pydantic import BaseModel

DEFAULT_MODEL = "claude-opus-4-8"
MODEL = os.environ.get("RECIPE_PARSER_MODEL", DEFAULT_MODEL)

_SYSTEM_PROMPT = (
    "You extract structured recipes from raw social media captions or video "
    "transcripts. Only use information present in the text - do not invent "
    "ingredients, quantities, or steps that aren't there. If a quantity isn't "
    "stated for an ingredient, omit it rather than guessing."
)


class ParsedIngredient(BaseModel):
    name: str
    quantity: str | None = None
    raw_text: str


class ParsedRecipe(BaseModel):
    title: str
    ingredients: list[ParsedIngredient]
    steps: list[str]
    cuisine: str | None = None


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
