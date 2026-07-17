from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.api.schemas import (
    IngestRequest,
    IngredientResponse,
    MatchRequest,
    RecipeMatchResponse,
    RecipeResponse,
)
from app.ingestion.manual import EmptyCaptionError, EmptySourceUrlError
from app.ingestion.pipeline import ingest_manual_caption, ingest_youtube
from app.ingestion.youtube import NoCaptionsAvailableError, YouTubeFetchError
from app.matching.ingredient_matcher import MatchableIngredient, MatchableRecipe, match_recipes
from app.models import Recipe
from app.parsing.recipe_parser import RecipeParseError

router = APIRouter()

_INGESTION_ERRORS = (
    YouTubeFetchError,
    NoCaptionsAvailableError,
    RecipeParseError,
    EmptyCaptionError,
    EmptySourceUrlError,
)


def _recipe_to_response(recipe: Recipe) -> RecipeResponse:
    return RecipeResponse(
        id=recipe.id,
        title=recipe.title,
        source_url=recipe.source_url,
        source_platform=recipe.source_platform,
        steps=recipe.steps,
        ingredients=[
            IngredientResponse(name=ri.ingredient.name, quantity=ri.quantity)
            for ri in recipe.ingredients
        ],
        cuisine=recipe.cuisine,
        meal_type=recipe.meal_type,
        cook_time_minutes=recipe.cook_time_minutes,
        created_at=recipe.created_at,
    )


def _to_matchable(recipe: Recipe) -> MatchableRecipe:
    return MatchableRecipe(
        id=recipe.id,
        title=recipe.title,
        ingredients=[MatchableIngredient(name=ri.ingredient.name) for ri in recipe.ingredients],
    )


@router.post("/recipes/ingest", response_model=RecipeResponse, status_code=201)
def ingest_recipe(
    payload: IngestRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> RecipeResponse:
    try:
        if payload.source_platform == "youtube":
            recipe = ingest_youtube(db, user_id, payload.url)
        else:
            if not payload.caption_text:
                raise HTTPException(
                    status_code=422,
                    detail="caption_text is required for non-YouTube sources",
                )
            recipe = ingest_manual_caption(
                db, user_id, payload.url, payload.caption_text, payload.source_platform
            )
    except _INGESTION_ERRORS as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.commit()
    db.refresh(recipe)
    return _recipe_to_response(recipe)


@router.get("/recipes", response_model=list[RecipeResponse])
def list_recipes(
    cuisine: str | None = Query(None),
    meal_type: str | None = Query(None),
    max_cook_time_minutes: int | None = Query(None, ge=0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[RecipeResponse]:
    query = select(Recipe).where(Recipe.user_id == user_id)
    if cuisine is not None:
        query = query.where(Recipe.cuisine == cuisine)
    if meal_type is not None:
        query = query.where(Recipe.meal_type == meal_type)
    if max_cook_time_minutes is not None:
        query = query.where(Recipe.cook_time_minutes <= max_cook_time_minutes)

    recipes = db.scalars(query.order_by(Recipe.created_at.desc())).all()
    return [_recipe_to_response(r) for r in recipes]


@router.post("/match", response_model=list[RecipeMatchResponse])
def match_pantry(
    payload: MatchRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[RecipeMatchResponse]:
    recipes = db.scalars(select(Recipe).where(Recipe.user_id == user_id)).all()
    recipe_by_id = {r.id: r for r in recipes}
    matches = match_recipes(payload.pantry, [_to_matchable(r) for r in recipes])

    return [
        RecipeMatchResponse(
            recipe=_recipe_to_response(recipe_by_id[m.recipe.id]),
            matched_ingredients=m.matched_ingredients,
            missing_ingredients=m.missing_ingredients,
            match_ratio=m.match_ratio,
        )
        for m in matches
    ]
