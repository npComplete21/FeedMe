# ADR 0017: Signed task tokens for ingestion status polling

Status: Accepted

## Context

`GET /recipes/ingest/{task_id}` was the only route on the authenticated router that didn't scope its
answer to the calling user. Every sibling route filters on `Recipe.user_id == user_id`; this one
passed the task id straight to Celery's result backend, which is keyed by task id alone and has no
concept of ownership. Any authenticated account could therefore poll any other account's ingestion
task and read the parsed recipe out of the success payload. Task ids are UUIDs so it wasn't
practically exploitable, but it became a real authorization gap once accounts were genuinely
distinct people (see [ADR-0015](0015-jwt-multi-user-auth.md)) rather than one hardcoded user.

Three ways to give the API an owner to check against:

1. **Embed `user_id` in the task's return value.** Rejected: a result only exists once the task
   *finishes*. The UI polls in a loop while the task is pending, and those polls would have nothing
   to check — leaving unprotected exactly the window the fix exists to close.
2. **Store a `task_id -> user_id` mapping in Redis at enqueue time.** Works, and is the obvious
   approach. Costs a write per ingest and a read per poll, and introduces a TTL that has to be kept
   longer than Celery's own result expiry — if the mapping expires first, a legitimate user gets a
   spurious 404 on their own task. A rare, confusing failure mode to own.
3. **Return a signed token instead of the raw task id.**

## Decision

**Take option 3.** `POST /recipes/ingest` returns a JWT containing `{task_id, user_id}` signed with
the existing `JWT_SECRET_KEY`, in the same `task_id` response field as before. `GET
/recipes/ingest/{task_id}` verifies the signature, checks the embedded `user_id` against the
authenticated caller, and only then queries Celery with the unwrapped task id.

Three things made this the better fit here over option 2:

- The machinery already exists — `app/api/auth.py` holds the signing key and `jwt` import, so this
  is a handful of lines rather than a new Redis dependency in the request path.
- **No new failure mode.** Nothing is stored, so there is no TTL to align with Celery's result
  expiry and no way for the ownership record and the result to disappear at different times.
- **The UI needed no change at all.** `app/ui/streamlit_app.py` already treats `task_id` as opaque:
  it reads the value from the response and passes it straight back into the poll URL, never
  inspecting it. Swapping one opaque string for another is invisible to it.

**Both token kinds carry a `typ` claim, and each decoder requires its own.** This is load-bearing,
not decoration: the two kinds share a signing secret, and a task token deliberately has no `exp`
(it only ever grants access to a task the caller already owned, and Celery expires the underlying
result anyway). Without `typ`, a task token — which carries a `user_id` — would validate as a login
token, i.e. a permanent, non-expiring credential. Tests cover both directions of that confusion.

**Unauthorized polls return 404, not 403.** Answering "that task exists but isn't yours" would
itself confirm that another user has an ingestion in flight.

## Consequences

- Gain: the route is scoped to the caller like every other route, with no new state to manage.
- Cost: the returned `task_id` is longer than a UUID and no longer human-readable — recovering the
  Celery id for debugging means decoding the token first.
- Cost: adding `typ` to access tokens invalidates every outstanding login once, on deploy. Trivial
  here (nothing is publicly deployed yet, and tokens are 14-day anyway), but it is a real one-time
  logout.
- Cost: rotating `JWT_SECRET_KEY` now also invalidates in-flight ingestion polls, not just logins.
  Harmless — the ingestion still completes and the recipe still appears in `GET /recipes`.
- Revisit when: task status needs to be readable by someone other than the enqueuer (e.g. an admin
  view), at which point a real stored ownership record — option 2 — becomes the better shape.
