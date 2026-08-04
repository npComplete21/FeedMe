from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.parsing.recipe_parser import Cuisine, MealType


class RegisterRequest(BaseModel):
    email: str
    password: str
    registration_code: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str


class IngestRequest(BaseModel):
    source_platform: Literal["youtube", "instagram"]
    url: str
    caption_text: str | None = None


class IngestAcceptedResponse(BaseModel):
    task_id: str


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


class IngestStatusResponse(BaseModel):
    state: Literal["pending", "success", "failure"]
    recipe: RecipeResponse | None = None
    error: str | None = None


class MatchRequest(BaseModel):
    pantry: list[str]


class RecipeMatchResponse(BaseModel):
    recipe: RecipeResponse
    matched_ingredients: list[str]
    missing_ingredients: list[str]
    match_ratio: float


class ChatRequest(BaseModel):
    message: str
    # Opaque provider-shaped conversation history, echoed back verbatim by the
    # client each turn (API is stateless) - not modeled field-by-field since
    # its shape is Anthropic's message/content-block format, not ours.
    history: list[dict] = []


class ChatResponse(BaseModel):
    reply: str
    history: list[dict]
