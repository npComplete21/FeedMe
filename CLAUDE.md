# FeedMe

A personal recipe app: collects recipes saved from Instagram/YouTube, parses them with Claude into
structured data, and lets you search "what can I make?" against ingredients you have on hand.

## Start here, every session

Before doing anything else, read:
1. [docs/roadmap.md](docs/roadmap.md) — phase-by-phase plan with checkboxes; tells you exactly what's
   done and what's next
2. [docs/backlog.md](docs/backlog.md) — deferred follow-ups noticed along the way but not yet acted on
3. [docs/adr/](docs/adr/) — one file per non-trivial technical decision, with the *why*. Check this
   before re-deciding something already settled.

## Standing conventions

- **Commit and push after every completed roadmap subphase** (e.g. 1.4, 1.5) — don't batch multiple
  subphases into one commit, and don't wait to be asked.
- **Write an ADR** (`docs/adr/000N-name.md`, follow the existing numbering) for any non-obvious
  technical choice, same format as the existing ones: Context / Decision / Consequences.
- **Testing**: pytest, real Postgres for DB tests (not sqlite) via the `db_session` fixture in
  `tests/conftest.py`, mock external calls (`yt-dlp`, Anthropic API) in unit tests, mark real-API
  tests `@pytest.mark.integration` (excluded from the default `pytest` run).
- When adding a feature that touches DB/API/UI, build bottom-up (persistence → API → UI) and verify
  each layer with tests before moving to the next, same as every phase so far.
- For UI changes, actually exercise them live (`docker compose up -d`, run `uvicorn` and `streamlit`,
  drive the browser) before calling the work done — don't rely on code review alone.

## Local dev

```
docker compose up -d                              # Postgres (only needed once per boot; check `docker ps` first)
.venv/bin/alembic upgrade head                     # apply any new migrations
.venv/bin/uvicorn app.main:app --reload             # backend, port 8000
.venv/bin/streamlit run app/ui/streamlit_app.py     # UI, port 8501
.venv/bin/pytest                                    # full test suite (unit only, integration excluded)
```

`ANTHROPIC_API_KEY` lives in `.env` (gitignored), auto-loaded via `python-dotenv` in both entry
points — no manual `export` needed.

## Architecture at a glance

FastAPI backend (`app/api`, `app/ingestion`, `app/parsing`, `app/persistence`, `app/matching`) +
Streamlit UI (`app/ui`) as two separate processes talking over HTTP — the UI is deliberately a thin
HTTP client with no direct imports of backend code (see ADR-0004), since Phase 2 dockerizes them
into separate images. Postgres runs in Docker locally; `app/models.py` + Alembic migrations define
the schema.
