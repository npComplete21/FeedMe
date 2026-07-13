# ADR 0003: FastAPI over Django

Status: Accepted

## Context

The backend needs to: call out to slow I/O-bound services (video/caption fetch via `yt-dlp`, the
Anthropic API for parsing and chat) without blocking; expose a clean API for a UI that will
change shape over time (Streamlit now, possibly a separate frontend later); and validate
LLM-produced JSON against a schema before persisting it. We don't need a built-in admin panel,
a batteries-included ORM, or server-rendered templating — Django's core strengths — since the UI
is a separate layer talking over HTTP.

## Decision

Use FastAPI as the backend framework, with SQLAlchemy for the ORM/migrations layer and Pydantic
models for request/response and LLM-output validation.

## Consequences

- Gain: native async support, which matters directly for the ingestion pipeline (network calls
  to yt-dlp/Instagram/Anthropic dominate request latency)
- Gain: automatic OpenAPI docs, useful both for our own Streamlit client and for debugging via
  the interactive `/docs` page
- Gain: Pydantic schemas double as the validation layer for LLM-parsed recipe JSON, so there's
  one schema definition instead of two
- Give up: Django's built-in admin UI, auth scaffolding, and ORM — acceptable since auth is
  being built deliberately minimal-first ([ADR-0002](0002-user-id-scoping-from-day-one.md)) and
  an admin UI isn't a current need
- Revisit if: the project grows into needing a full content-management-style admin interface,
  where Django's batteries would start paying for themselves
