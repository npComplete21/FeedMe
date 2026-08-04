# FeedMe — Backlog

A running list of follow-ups noticed along the way that aren't part of the current phase's scope.
Unlike [roadmap.md](roadmap.md) (the structured, phased plan), this is unordered — just a place to
not lose track of things. When an item's time comes, either fold it into the roadmap as a real
phase item, or knock it out directly and remove it from here.

Each entry: what it is, why it matters, and where it came from (so it doesn't rot into a mystery
bullet point six months from now).

---

- [ ] **Backfill existing duplicate `Ingredient` rows.** Phase 1.1's normalization fix
  (parenthetical stripping + synonym map, see [ADR-0008](adr/0008-ingredient-normalization-alias-map.md))
  only applies to *new* ingredients going forward — it doesn't retroactively merge rows that were
  already created before the fix (e.g. the real `"onions"` / `"onion (for cooking)"` /
  `"onion (for blender)"` duplicates from live testing). Needs a one-off script: find `Ingredient`
  rows whose normalized names collide, repoint their `RecipeIngredient` rows to one canonical row,
  delete the duplicates. *Noted: 2026-07-16, during Phase 1.1.*

- [ ] **Watch for drift between the UI's hardcoded `CUISINES`/`MEAL_TYPES` lists and the backend's
  `Cuisine`/`MealType` Literal types.** Deliberately duplicated rather than imported (see
  [ADR-0009](adr/0009-tags-closed-vocabulary.md)) to keep the UI a pure HTTP client with no backend
  imports. If the allowed values change often enough that this becomes annoying, consider a shared
  constants module both sides can depend on without pulling in `anthropic`/`sqlalchemy`.
  *Noted: 2026-07-17, during Phase 1.2.*

- [ ] **Containers run as root.** Celery logs a security warning on startup (`ROOT_DISCOURAGED`) and
  none of the Dockerfiles (`docker/api.Dockerfile`, `docker/ui.Dockerfile`, `docker/worker.Dockerfile`)
  create/use a non-root user. Fine for a local-only Docker Compose stack; worth fixing (add a user,
  `chown` the app dir, `USER` directive) before Phase 3 actually exposes any of this to the internet.
  *Noted: 2026-08-03, during Phase 2.2.*

- [ ] **`GET /recipes/ingest/{task_id}` doesn't scope by `user_id`.** Any authenticated user can poll
  any other user's Celery task ID for ingestion status/result, since the task_id → result lookup goes
  straight to Celery's result backend with no ownership check. Low practical risk (task IDs are
  UUIDs, not guessable), but a real gap now that accounts are genuinely distinct people rather than
  one hardcoded user. Fix: store `user_id` alongside the task at enqueue time (or embed it in the
  task result) and check it in `app/api/routes.py`'s `ingest_status` handler.
  *Noted: 2026-08-04, during Phase 4 (see [ADR-0015](adr/0015-jwt-multi-user-auth.md)).*
