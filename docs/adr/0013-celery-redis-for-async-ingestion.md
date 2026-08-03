# ADR 0013: Celery + Redis for background recipe ingestion

Status: Accepted

## Context

`POST /recipes/ingest` ran the entire pipeline synchronously inside the HTTP request: fetch the
YouTube transcript (network call), parse it with Claude (the slowest step, several seconds), then
persist. Two concrete problems: nothing retried a transient failure (a YouTube hiccup, an Anthropic
rate limit), and a slow ingest tied up a request thread for the whole duration. The roadmap called
for "Celery + Redis (non-blocking, retryable)" - this ADR records why that pairing, not an
alternative, and how the retry/terminal split works.

### Why Redis, not Kafka

Kafka is a distributed, durable, replayable event log - built for many independent consumers reading
the same stream at their own pace, and for reprocessing history. Our problem is a plain work queue:
exactly one thing needs to happen per ingest request (run the pipeline once), consumed by exactly one
worker. That's the shape Celery+Redis is built for, not Kafka's. Concretely: Celery has no
first-class Kafka broker support (Redis and RabbitMQ are its native backends); Kafka needs a cluster
to run well, versus one `redis:7-alpine` container with no configuration; and we also need a place to
answer "what's the status of task X," which Redis already gives us as its second role (the result
backend) - Kafka has no equivalent and would need a second store bolted on anyway. Kafka earns its
complexity at real throughput and multi-consumer fan-out, neither of which describes a personal
recipe app doing a handful of ingests a day. Revisit if that changes - see Consequences.

## Decision

**The ingest endpoint enqueues instead of executing.** `POST /recipes/ingest` (`app/api/routes.py`)
now calls `ingest_youtube_task.delay(...)` / `ingest_manual_caption_task.delay(...)` and returns
`202 Accepted` with a `task_id` immediately - it never touches the DB or calls Claude itself anymore.
A new `GET /recipes/ingest/{task_id}` does a stateless point-in-time read of Celery's result backend
(`AsyncResult(task_id).state`) and reports `pending` / `success` / `failure`. The Streamlit UI
(`app/ui/streamlit_app.py`) polls that endpoint every 2 seconds inside a `st.status(...)` block until
it resolves - chosen over a "submit and check back later" UX because it's a smaller behavior change
for daily use, and Streamlit's rerun model makes a polling loop cheap to write.

**`app/worker.py` is the new module**: one `Celery` app (broker and result backend both Redis), and
two thin task functions that call the *unchanged* `ingest_youtube()` / `ingest_manual_caption()`
pipeline functions from `app/ingestion/pipeline.py`. All the transaction handling and retry
classification is factored into one shared `_run_ingest_task()` helper rather than duplicated per
task, and its DB session is injected via a `session_factory` parameter (defaulting to `SessionLocal`)
specifically so it's unit-testable with a fake session instead of a real Postgres connection.

**Retryable vs. terminal is decided by exception type**, not by inspecting messages:

| Retryable (transient - worth `self.retry()`) | Terminal (retrying can't help - let it fail) |
|---|---|
| `YouTubeFetchError` | `NoCaptionsAvailableError` |
| `httpx.HTTPError` | `RecipeParseError` (model refusal) |
| `anthropic.APIConnectionError` | `EmptyCaptionError` / `EmptySourceUrlError` |
| `anthropic.RateLimitError` | |
| `anthropic.InternalServerError` | |

No new exception types were introduced for the transient cases - the retryable ones are generic
infrastructure failures (network, rate limit, 5xx) that can happen at any network call, not
domain-specific like "no captions" is, so they're caught directly by SDK/library type in
`app/worker.py` rather than wrapped at the source. Retries are capped at 3, with a 10-second delay
(short deliberately - a user is actively watching the poll loop, not fine with Celery's 3-minute
default).

**Only the `api` container runs migrations.** `docker/worker.Dockerfile` reuses the `api` extras
group (it needs the same pipeline dependencies, plus `celery`/`redis`) but does not run
`alembic upgrade head` - same single-owner reasoning as ADR-0012, now also protecting against a
second kind of race: a worker container starting before the schema migration the new code expects
has actually been applied.

## Consequences

- Gain: ingestion no longer blocks a request thread, and transient failures (a YouTube blip, an
  Anthropic rate limit) now recover automatically instead of surfacing as a hard error the user has
  to manually retry.
- Gain: the actual pipeline code (`app/ingestion/pipeline.py` and everything it calls) is completely
  unchanged - only *where* it's invoked from changed, from a request handler to a task function.
- Cost: ingestion failures are no longer instant. A bad caption or invalid URL used to 422
  immediately; now it takes at least one poll cycle (~2s) to surface, since that validation happens
  inside the task rather than the route. Accepted as a minor UX regression rather than restructuring
  validation to run twice (once fast-path in the route, once for real in the task).
- Cost: no permanent ingestion history. Celery's result backend (Redis) answers "is my ingest done"
  for the session it happened in, but results expire and there's no durable audit table of past
  attempts. Acceptable for now - flag if ingestion history becomes an actual wanted feature, at which
  point it's an additive table, not a redesign.
- Revisit if: FeedMe ever needs multiple independent systems reacting to "a recipe was ingested"
  (search indexing, notifications, analytics, each consuming independently) or needs to replay past
  ingestions - that's exactly when Kafka's model starts earning its complexity over Redis's.
