from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.converters import recipe_to_response
from app.api.deps import get_current_user_id, get_db, require_auth_token
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    IngestAcceptedResponse,
    IngestRequest,
    IngestStatusResponse,
    MatchRequest,
    RecipeMatchResponse,
    RecipeResponse,
    RecipeUpdateRequest,
)
from app.chat.recipe_chat import RecipeChatError, chat_about_recipes
from app.matching.ingredient_matcher import MatchableIngredient, MatchableRecipe, match_recipes
from app.models import Recipe
from app.persistence.recipe_store import IngredientSpec, update_recipe
from app.worker import celery_app, ingest_manual_caption_task, ingest_youtube_task

router = APIRouter(dependencies=[Depends(require_auth_token)])


def _to_matchable(recipe: Recipe) -> MatchableRecipe:
    return MatchableRecipe(
        id=recipe.id,
        title=recipe.title,
        ingredients=[MatchableIngredient(name=ri.ingredient.name) for ri in recipe.ingredients],
    )


@router.post("/recipes/ingest", response_model=IngestAcceptedResponse, status_code=202)
def ingest_recipe(
    payload: IngestRequest,
    user_id: int = Depends(get_current_user_id),
) -> IngestAcceptedResponse:
    if payload.source_platform == "youtube":
        result = ingest_youtube_task.delay(user_id, payload.url)
    else:
        if not payload.caption_text:
            raise HTTPException(
                status_code=422,
                detail="caption_text is required for non-YouTube sources",
            )
        result = ingest_manual_caption_task.delay(
            user_id, payload.url, payload.caption_text, payload.source_platform
        )

    return IngestAcceptedResponse(task_id=result.id)


@router.get("/recipes/ingest/{task_id}", response_model=IngestStatusResponse)
def ingest_status(task_id: str) -> IngestStatusResponse:
    result = AsyncResult(task_id, app=celery_app)

    if result.successful():
        return IngestStatusResponse(state="success", recipe=RecipeResponse(**result.result))
    if result.failed():
        return IngestStatusResponse(state="failure", error=str(result.result))
    return IngestStatusResponse(state="pending")


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
    return [recipe_to_response(r) for r in recipes]


@router.put("/recipes/{recipe_id}", response_model=RecipeResponse)
def update_recipe_route(
    recipe_id: int,
    payload: RecipeUpdateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> RecipeResponse:
    recipe = db.scalars(
        select(Recipe).where(Recipe.id == recipe_id, Recipe.user_id == user_id)
    ).first()
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    recipe = update_recipe(
        db,
        recipe,
        title=payload.title,
        steps=payload.steps,
        cuisine=payload.cuisine,
        meal_type=payload.meal_type,
        cook_time_minutes=payload.cook_time_minutes,
        ingredients=[
            IngredientSpec(name=i.name, quantity=i.quantity) for i in payload.ingredients
        ],
    )
    db.commit()
    db.refresh(recipe)
    return recipe_to_response(recipe)


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
            recipe=recipe_to_response(recipe_by_id[m.recipe.id]),
            matched_ingredients=m.matched_ingredients,
            missing_ingredients=m.missing_ingredients,
            match_ratio=m.match_ratio,
        )
        for m in matches
    ]


@router.post("/chat", response_model=ChatResponse)
def chat_with_assistant(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> ChatResponse:
    try:
        result = chat_about_recipes(db, user_id, payload.message, history=payload.history)
    except RecipeChatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ChatResponse(reply=result.reply, history=result.messages)
