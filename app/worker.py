from __future__ import annotations

import os
from collections.abc import Callable

import anthropic
import httpx
from celery import Celery
from sqlalchemy.orm import Session

from app.api.converters import recipe_to_response
from app.db import SessionLocal
from app.ingestion.pipeline import ingest_manual_caption, ingest_youtube
from app.ingestion.youtube import YouTubeFetchError
from app.models import Recipe

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("feedme", broker=REDIS_URL, backend=REDIS_URL)

# Errors worth retrying: transient network/API hiccups where the identical
# request will likely succeed a moment later. Everything else - bad captions,
# a model refusal, invalid user input (see the ingestion/parsing modules for
# those types) - is terminal: retrying can't change the outcome, so those are
# left to propagate and fail the task immediately rather than burn retries.
_RETRYABLE_ERRORS = (
    YouTubeFetchError,
    httpx.HTTPError,
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


def _run_ingest_task(
    self: Celery,
    run: Callable[[Session], Recipe],
    *,
    session_factory: Callable[[], Session] = SessionLocal,
) -> dict:
    """Shared transaction/retry handling for both ingest tasks below - keeps
    the DB session lifecycle and retry classification in one place rather
    than duplicated per task. session_factory is injectable so tests can pass
    a fake session without a real DB connection."""
    db = session_factory()
    try:
        recipe = run(db)
        db.commit()
        return recipe_to_response(recipe).model_dump(mode="json")
    except _RETRYABLE_ERRORS as exc:
        db.rollback()
        raise self.retry(exc=exc) from exc
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def ingest_youtube_task(self, user_id: int, url: str) -> dict:
    return _run_ingest_task(self, lambda db: ingest_youtube(db, user_id, url))


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def ingest_manual_caption_task(
    self, user_id: int, url: str, caption_text: str, source_platform: str = "instagram"
) -> dict:
    return _run_ingest_task(
        self,
        lambda db: ingest_manual_caption(db, user_id, url, caption_text, source_platform),
    )
