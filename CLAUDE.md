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
- For UI changes, actually exercise them live (either the venv workflow or `docker compose up -d --build`,
  drive the browser) before calling the work done — don't rely on code review alone.

## Local dev

**Fast iteration (hot-reload, one component at a time):**
```
docker compose up -d db redis                     # Postgres + Redis only (check `docker ps` first)
.venv/bin/alembic upgrade head                     # apply any new migrations
.venv/bin/uvicorn app.main:app --reload             # backend, port 8000
.venv/bin/celery -A app.worker worker --loglevel=info  # background worker, for ingestion
.venv/bin/streamlit run app/ui/streamlit_app.py     # UI, port 8501
.venv/bin/pytest                                    # full test suite (unit only, integration excluded)
```
Recipe ingestion is async (Celery + Redis, see ADR-0013) — the worker process above must be running
or `POST /recipes/ingest` will accept the request and enqueue it, but nothing will ever pick it up.
Fresh venv setup: `pip install -e ".[api,ui,dev]"` (deps are split into `api`/`ui`/`dev` extras in
`pyproject.toml` — see ADR-0012 — combine all three for local dev).

**Full containerized stack (closer to how it'll actually run):**
```
docker compose up -d --build      # Postgres + Redis + API + worker + UI, migrations run automatically
docker compose logs -f worker                      # tail the worker specifically — that's where
                                                     # ingestion (yt-dlp fetch + Claude parse) runs
docker compose down                                # stop everything (add -v to also wipe the DB volume)
```
Use this to verify a change works the way it will in production, not just against your venv.

`ANTHROPIC_API_KEY` lives in `.env` (gitignored) — auto-loaded via `python-dotenv` for the venv
workflow, and injected into the `api` container via `env_file: .env` in `docker-compose.yml` for the
containerized workflow (never baked into the image itself). The `ui` service doesn't get this
variable at all — it has no use for it (see ADR-0004 / ADR-0012).

## Architecture at a glance

FastAPI backend (`app/api`, `app/ingestion`, `app/parsing`, `app/persistence`, `app/matching`) +
Streamlit UI (`app/ui`) as separate processes talking over HTTP — the UI is deliberately a thin HTTP
client with no direct imports of backend code (see ADR-0004). Recipe ingestion runs on a separate
Celery worker (`app/worker.py`), not the request thread — `POST /recipes/ingest` enqueues a task via
Redis and returns immediately; the UI polls `GET /recipes/ingest/{task_id}` until it resolves (see
ADR-0013). API, UI, and worker are each Dockerized as separate images (`docker/*.Dockerfile`, see
ADR-0012/0013), wired together with Postgres and Redis in `docker-compose.yml`. `app/models.py` +
Alembic migrations define the schema; migrations run automatically in the `api` container's
entrypoint before it starts serving — the `worker` container deliberately does not also run them,
to keep a single owner of schema changes.
