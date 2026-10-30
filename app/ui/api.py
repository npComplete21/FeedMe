"""The UI's HTTP client for the FeedMe API.

Pages call `api.get_client()` through the module (not `from app.ui.api import
get_client`) so tests can monkeypatch it. The UI never imports backend code; it
only talks to the API over HTTP (ADR-0004).
"""

import os
import time

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.environ.get("FEEDME_API_URL", "http://localhost:8000")

# Polling an ingest task (the Save tab, ADR-0013): one GET every couple of
# seconds, giving up after two minutes. Celery reports a lost or expired task as
# PENDING forever, so without a deadline a dead worker means an endless spinner.
INGEST_POLL_SECONDS = 2
INGEST_DEADLINE_SECONDS = 120


def now() -> float:
    """The clock the ingest deadline is measured on. Tests monkeypatch it."""
    return time.monotonic()


def sleep(seconds: float) -> None:
    """The wait between ingest polls. Tests monkeypatch it (rather than
    `time.sleep` itself, which AppTest's own wait loop uses)."""
    time.sleep(seconds)


def error_detail(exc: httpx.HTTPStatusError) -> str:
    """The API's `detail` message for a failed call, or the raw body if it has none."""
    try:
        return exc.response.json().get("detail", exc.response.text)
    except ValueError:
        return exc.response.text


def _handle_response(response: httpx.Response) -> None:
    # Global 401 handler: an expired or invalidated token drops the user back to
    # the login screen from any tab, instead of every call site needing its own
    # expiry check.
    if response.status_code == 401:
        # Imported here, not at the top: auth imports this module for
        # API_BASE_URL and error_detail.
        from app.ui import auth

        auth.log_out()
        st.rerun()


def get_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """A client for the API, authenticated as the logged-in user.

    `transport` is for tests only (an `httpx.MockTransport`); the app never passes it.
    """
    return httpx.Client(
        base_url=API_BASE_URL,
        timeout=60.0,
        headers={"Authorization": f"Bearer {st.session_state.access_token}"},
        event_hooks={"response": [_handle_response]},
        transport=transport,
    )
