from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class IngestRequest(BaseModel):
    source_platform: Literal["youtube", "instagram"]
    url: str
    caption_text: str | None = None


class IngredientResponse(BaseModel):
    name: str
    quantity: str | None = None


class RecipeResponse(BaseModel):
    id: int
    title: str
    source_url: str
    source_platform: str
    steps: list[str]
    ingredients: list[IngredientResponse]
    created_at: datetime


class MatchRequest(BaseModel):
    pantry: list[str]


class RecipeMatchResponse(BaseModel):
    recipe: RecipeResponse
    matched_ingredients: list[str]
    missing_ingredients: list[str]
    match_ratio: float
