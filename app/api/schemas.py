from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.parsing.recipe_parser import Cuisine, MealType


class IngestRequest(BaseModel):
    source_platform: Literal["youtube", "instagram"]
    url: str
    caption_text: str | None = None


class IngredientResponse(BaseModel):
    name: str
    quantity: str | None = None


class IngredientUpdate(BaseModel):
    name: str
    quantity: str | None = None


class RecipeUpdateRequest(BaseModel):
    title: str
    steps: list[str]
    cuisine: Cuisine | None = None
    meal_type: MealType | None = None
    cook_time_minutes: int | None = None
    ingredients: list[IngredientUpdate]


class RecipeResponse(BaseModel):
    id: int
    title: str
    source_url: str
    source_platform: str
    steps: list[str]
    ingredients: list[IngredientResponse]
    cuisine: str | None = None
    meal_type: str | None = None
    cook_time_minutes: int | None = None
    created_at: datetime


class MatchRequest(BaseModel):
    pantry: list[str]


class RecipeMatchResponse(BaseModel):
    recipe: RecipeResponse
    matched_ingredients: list[str]
    missing_ingredients: list[str]
    match_ratio: float
