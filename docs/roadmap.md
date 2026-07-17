# FeedMe — Roadmap

Living document. Update this as scope changes — check items off, reorder, add/remove steps.
Each phase links to the ADRs ([docs/adr/](adr/)) that explain *why* a given technical choice was made.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Phase 0 — Local MVP

Goal: prove the ingest → parse → store → match loop works, running only on your laptop.

- [x] 0.1 Project skeleton + test harness (FastAPI shell, `docker-compose.yml` with Postgres, pytest wired to a health-check route)
- [x] 0.2 DB models + migrations — `User`, `Recipe`, `Ingredient`, `RecipeIngredient` (see [ADR-0001](adr/0001-postgres-over-nosql.md), [ADR-0002](adr/0002-user-id-scoping-from-day-one.md))
- [x] 0.3 YouTube ingestion — URL in, raw transcript/caption out (via `yt-dlp`)
- [x] 0.4 Manual caption ingestion — Instagram path, paste caption text + URL (see [ADR-0006](adr/0006-raw-source-staging-table.md))
- [x] 0.5 LLM parsing — raw text in, structured `Recipe` JSON out, validated against a Pydantic schema (see [ADR-0007](adr/0007-llm-structured-extraction.md))
- [x] 0.6 Persistence — wire 0.5's output into 0.2's models, scoped by `user_id` (resolves [ADR-0006](adr/0006-raw-source-staging-table.md)'s deferred `raw_source_id` link)
- [x] 0.7 Ingredient matching — pure function, pantry list in, ranked recipes out
- [x] 0.8 API layer — `POST /recipes/ingest`, `GET /recipes`, `POST /match` (see [ADR-0003](adr/0003-fastapi-over-django.md))
- [x] 0.9 Minimal UI — Streamlit, thin layer over the API (see [ADR-0004](adr/0004-streamlit-for-phase-0-ui.md))

Each step ships with its own tests before moving to the next (see testing approach below).

**Phase 0 complete.** Full loop verified live: paste a caption → parse (blocked here only by no
`ANTHROPIC_API_KEY` in the dev sandbox, and confirmed the failure surfaces as a clean UI error
rather than a crash) → browse recipes → match against a pantry, all exercised through the actual
running FastAPI + Streamlit servers against real Postgres, not just the test suite.

## Phase 1 — Make it good

- [x] 1.1 Ingredient synonym handling — shared `normalize_ingredient_name()`, alias map + parenthetical stripping (see [ADR-0008](adr/0008-ingredient-normalization-alias-map.md))
- [x] 1.2 Tags/filters — cuisine, meal type, cook time (see [ADR-0009](adr/0009-tags-closed-vocabulary.md))
- [ ] 1.3 In-app recipe editing to fix bad LLM parses
- [ ] 1.4 LLM chat over your recipes ("I have chicken, rice, broccoli — what should I make?")

## Phase 2 — Productionize

- [ ] Dockerize everything (API, worker, UI)
- [ ] Move ingestion to Celery + Redis (non-blocking, retryable)
- [ ] Add auth — starts single-user-token, designed to extend to real multi-user auth
- [ ] Tests for parsing/matching logic (if not already covered in Phase 0)
- [ ] Full docker-compose stack (Postgres, Redis, backend, worker, UI)

## Phase 3 — Ship to AWS / k8s

- [ ] Decide EKS vs k3s (see [ADR-0005](adr/0005-k3s-vs-eks.md) — currently **proposed**, not yet decided)
- [ ] ECR for images
- [ ] Kubernetes manifests or Helm chart — Deployment/Service/Ingress for API, worker
- [ ] RDS Postgres (or in-cluster Postgres, depending on ADR-0005 outcome)
- [ ] Secrets for API keys, ConfigMap for env
- [ ] GitHub Actions — build, push, deploy on merge to main
- [ ] TLS via cert-manager + Route53

## Phase 4 — Multi-user + polish

- [ ] Real multi-user auth (this is where [ADR-0002](adr/0002-user-id-scoping-from-day-one.md) pays off)
- [ ] PWA / share-sheet shortcut for faster link capture
- [ ] Recipe photos, ratings, "cooked this" tracking
- [ ] Weekly meal-plan generator from pantry + recipe list
- [ ] Monitoring — CloudWatch or in-cluster Prometheus/Grafana, cost alerts

---

## Testing approach (applies across every phase)

- pytest for everything; `pytest-asyncio` for FastAPI's async routes
- Real Postgres for tests (not sqlite) — avoids drift from Postgres-specific behavior relied on later
- Mock external calls (`yt-dlp`, Anthropic API) in unit tests — fast, free, deterministic
- A small set of real-API integration tests, marked separately (`@pytest.mark.integration`), run by hand rather than on every save
