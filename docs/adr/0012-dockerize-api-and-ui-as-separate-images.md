# ADR 0012: Dockerize the API and UI as separate images, split by pyproject.toml extras

Status: Accepted

## Context

Phase 2's first item is containerizing the API and UI (the worker comes later, once Celery/Redis
exist). Two real design questions came up:

1. **One image or two?** ADR-0004 already anticipated this: the UI is a pure HTTP client with no
   direct imports of backend code, specifically so that "once Phase 2 splits the backend and UI
   into separate Docker images," the UI image wouldn't need `anthropic`/`sqlalchemy`/`yt-dlp`
   installed. Before this ADR, `pyproject.toml` had one flat `dependencies` list covering both -
   fine for a single local venv, wrong for two images with different footprints.
2. **When do database migrations run relative to the app starting?** A container needs the schema
   to already be correct before `uvicorn` starts serving traffic, but nothing was actually running
   `alembic upgrade head` anywhere outside a developer's manual terminal step.

## Decision

**Two images, split via `pyproject.toml` optional-dependency groups.** Added `api` and `ui` extras
(`docker/api.Dockerfile` installs `.[api]`, `docker/ui.Dockerfile` installs `.[ui]`) instead of a
separate `requirements-api.txt`/`requirements-ui.txt` - one file stays the single source of truth
for versions, same reasoning as ADR-0009's aversion to two copies of the same fact drifting apart.
Both Dockerfiles copy the *entire* `app/` source tree (not just their own subpackage) - simpler and
more robust than trying to get `setuptools`'s `packages.find` to discover a partial tree correctly,
and harmless: the UI image never installs `sqlalchemy`/`anthropic`/`yt-dlp`, so even though
`app/models.py` etc. physically exist in that image, nothing ever imports them (`streamlit_app.py`
never reaches into other `app.*` modules, per ADR-0004) and the missing heavy dependencies never
get exercised.

**Migrations run in the API container's entrypoint, before `uvicorn` starts:**
```
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```
Chosen over a separate one-off migration step/job because there's exactly one API replica in this
stack - no race between multiple containers all trying to migrate simultaneously, which is the
real risk this pattern has once there's more than one replica (see Consequences).

**`docker-compose.yml` wires the three services together** by Compose's internal service-name DNS
(`api`'s `DATABASE_URL` points at `db`, not `localhost`; `ui`'s `FEEDME_API_URL` points at `api`) -
the same environment variables the app already reads locally, just pointed at different hostnames.
The `db` service gained a `pg_isready` healthcheck, and `api` depends on it via
`condition: service_healthy` - without this, the API container could start migrating before
Postgres was actually accepting connections yet, since "container started" and "Postgres ready"
aren't the same moment.

`ANTHROPIC_API_KEY` reaches the `api` container via `env_file: .env` - injected into the running
container's environment at start time, never copied into the image itself. The `ui` service gets no
such env file; it has no use for that key (ADR-0004's "pure HTTP client" boundary holds exactly at
this line).

## Consequences

- Gain: the UI image is meaningfully smaller and never pulls in `anthropic`/`sqlalchemy`/`psycopg`/
  `yt-dlp` - exactly what ADR-0004 set out to avoid, now actually true rather than just planned for.
- Gain: `docker compose up -d --build` reproduces the entire stack (Postgres + API + UI) from a
  clean checkout, migrations included - verified live, including that existing data in the named
  `pgdata` volume survives a container recreate.
- Cost: both Dockerfiles copy the full `app/` tree, so there's some redundant unused source code
  sitting in the UI image (a few KB - not the heavy dependencies, which is what actually mattered).
- Cost: `alembic upgrade head` running in every API container's entrypoint is **only safe with a
  single API replica**. The moment this stack scales to multiple API instances (Phase 3, behind a
  load balancer or in Kubernetes), every replica would race to run migrations on startup
  simultaneously. Revisit then: pull the migration out into a separate one-off step (a Compose
  `run --rm`, or a Kubernetes init container/Job) that runs once, before any replica starts serving.
- Revisit if: `pip install ".[api]"` full-reinstall-per-build becomes a real iteration-speed pain -
  a multi-stage build or a frozen lockfile copied-in-first would let dependency layers cache
  separately from app code, at the cost of another artifact to keep in sync. Not worth it yet at
  this project's size.
