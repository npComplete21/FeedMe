from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from app.ingestion.youtube import NoCaptionsAvailableError, YouTubeFetchError
from app.parsing.recipe_parser import RecipeParseError
from app.worker import _run_ingest_task


class _FakeRetry(Exception):
    """Stand-in for the celery.exceptions.Retry that self.retry() would raise."""


def _fake_self() -> MagicMock:
    self = MagicMock()
    self.retry.side_effect = lambda exc: _FakeRetry(str(exc))
    return self


def _fake_recipe() -> MagicMock:
    recipe = MagicMock()
    recipe.id = 1
    recipe.title = "Fried Rice"
    recipe.source_url = "https://youtube.com/watch?v=abc"
    recipe.source_platform = "youtube"
    recipe.steps = ["cook rice"]
    recipe.ingredients = []
    recipe.cuisine = None
    recipe.meal_type = None
    recipe.cook_time_minutes = None
    from datetime import datetime, timezone

    recipe.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return recipe


def test_run_ingest_task_commits_and_returns_serialized_recipe():
    db = MagicMock()
    recipe = _fake_recipe()

    result = _run_ingest_task(_fake_self(), lambda _db: recipe, session_factory=lambda: db)

    assert result["title"] == "Fried Rice"
    db.commit.assert_called_once()
    db.close.assert_called_once()
    db.rollback.assert_not_called()


@pytest.mark.parametrize(
    "exc",
    [
        YouTubeFetchError("network blip"),
        httpx.ConnectError("connection reset"),
        anthropic.APIConnectionError(request=MagicMock()),
        anthropic.RateLimitError("rate limited", response=MagicMock(), body=None),
        anthropic.InternalServerError("server error", response=MagicMock(), body=None),
    ],
)
def test_run_ingest_task_retries_transient_errors(exc):
    db = MagicMock()
    self = _fake_self()

    def run(_db):
        raise exc

    with pytest.raises(_FakeRetry):
        _run_ingest_task(self, run, session_factory=lambda: db)

    self.retry.assert_called_once()
    db.rollback.assert_called_once()
    db.close.assert_called_once()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    "exc",
    [
        NoCaptionsAvailableError("no captions"),
        RecipeParseError("model declined"),
    ],
)
def test_run_ingest_task_does_not_retry_terminal_errors(exc):
    db = MagicMock()
    self = _fake_self()

    def run(_db):
        raise exc

    with pytest.raises(type(exc)):
        _run_ingest_task(self, run, session_factory=lambda: db)

    self.retry.assert_not_called()
    db.rollback.assert_called_once()
    db.close.assert_called_once()
