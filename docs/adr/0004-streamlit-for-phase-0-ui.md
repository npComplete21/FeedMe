# ADR 0004: Streamlit for the Phase 0 UI

Status: Accepted

## Context

Phase 0 needs *some* UI to exercise ingestion and matching end-to-end, but the actual UI
requirements aren't well understood yet (chat, browsing, editing all still evolving). Investing
in a full frontend (React/Next.js, a separate build toolchain, styling) before knowing what's
actually needed risks building the wrong thing, and adds a second language/toolchain to a
Python-first personal project.

## Decision

Use Streamlit for the earliest UI — recipe list, ingredient search box, and later the chat
interface — talking to the FastAPI backend over HTTP.

## Consequences

- Gain: fast to build, pure Python, no separate frontend toolchain to stand up or learn
  alongside everything else
- Give up: Streamlit's session model and styling are limiting for a production, multi-user,
  polished UI — this is explicitly a prototyping layer, not the final frontend
- Revisit: expect to replace this with a proper frontend once UI requirements stabilize, likely
  around Phase 3–4 when multi-user support and a less "developer tool"-shaped UI start to matter
