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
- [x] 1.3 In-app recipe editing to fix bad LLM parses (see [ADR-0010](adr/0010-recipe-edit-full-replace.md))
- [x] 1.4 LLM chat over your recipes ("I have chicken, rice, broccoli — what should I make?") (see [ADR-0011](adr/0011-chat-uses-tool-use-not-free-text-reasoning.md))

**Phase 1 complete.** Chat verified live against the real Anthropic API and real saved recipes,
including a multi-turn follow-up ("what if I also have gochujang and beef?") - caught and fixed a
real bug along the way where `tool_runner`'s `ParsedBetaTextBlock.parsed_output` field broke the
second API call when echoed back as conversation history.

## Phase 2 — Productionize

- [x] 2.1 Dockerize API + UI (see [ADR-0012](adr/0012-dockerize-api-and-ui-as-separate-images.md)) —
  worker image comes with 2.2, once Celery introduces something to dockerize
- [x] 2.2 Move ingestion to Celery + Redis (non-blocking, retryable) (see [ADR-0013](adr/0013-celery-redis-for-async-ingestion.md)) — includes dockerizing the worker
- [x] 2.3 Add auth — starts single-user-token, designed to extend to real multi-user auth (see [ADR-0014](adr/0014-single-shared-token-auth.md))
- [x] 2.4 Tests for parsing/matching logic — audited, not new work: `pytest --cov` shows 100%
  line *and* branch coverage on `app/parsing/recipe_parser.py`, `app/matching/ingredient_matcher.py`,
  and `app/ingredients/normalization.py`, and a manual read of `tests/parsing/`, `tests/matching/`,
  `tests/ingredients/` confirms it's real behavioral coverage (ties, empty pantry, zero-ingredient
  recipes, synonym/paren-stripping interaction order, refusal handling) - not just line-hits.
- [x] 2.5 Full docker-compose stack (Postgres, Redis, backend, worker, UI) — satisfied as a side
  effect of 2.1 + 2.2; all five services verified live together via `docker compose up -d --build`

**Phase 2 complete.**

## Phase 3 — Ship to Oracle Cloud / k3s

Hosting decided: Oracle Cloud's Always Free tier (Ampere A1, **2 OCPU/12GB** since 2026-06-15 —
Oracle halved it from 4/24 without announcement; the stack still fits), running k3s, chosen over
AWS on cost (see [ADR-0016](adr/0016-oracle-cloud-k3s-over-aws.md), supersedes
[ADR-0005](adr/0005-k3s-vs-eks.md)).

- [x] 3.1 Oracle Cloud account + Always Free Ampere A1 instance provisioned — `VM.Standard.A1.Flex`,
  2 OCPU / 12GB (10GB usable), 30GB disk, Oracle Linux 9.8 `aarch64`, SSH as `opc` with
  `~/.ssh/feedme_oracle`. Note the free-tier ARM allowance was **halved to 2 OCPU / 12GB** on
  2026-06-15; the 4 OCPU/24GB figure in [ADR-0016](adr/0016-oracle-cloud-k3s-over-aws.md) predates
  that. The stack still fits comfortably (~6GB of the 12GB ceiling).
- [x] 3.2 Networking — public subnet in `feedme-vcn`; OCI security list allows 22/80/443 inbound
  and nothing else (6443 verified filtered, so the Kubernetes API is not internet-facing);
  host `firewalld` disabled per k3s's guidance for RHEL-family, leaving the security list as the
  single boundary (see [ADR-0019](adr/0019-single-firewall-layer-on-the-node.md)).
  The public IP was since reserved in place (OCI supports this without the address changing).
- [x] 3.3 Install k3s on the instance — v1.36.4+k3s1, node Ready, `k3s-selinux` installed
  automatically so SELinux stays Enforcing. Bundled Traefik kept as the ingress controller for
  3.7; `local-path` is the default StorageClass that 3.5's PVC will bind to. `kubectl` works from
  the dev machine over an SSH tunnel (see CLAUDE.md) with 6443 still closed to the internet, and
  **3.5's manifests now validate clean against a real API server** (`kubectl apply -k k8s/
  --dry-run=server`), which was the outstanding gap from that step.
- [x] **Stack deployed and verified live on the cluster** — all five pods 1/1 with zero restarts,
  PVC bound, migrations applied by the init container. Full loop exercised against the real
  cluster: register → ingest a caption → Redis → worker → Claude → Postgres → match. Data and
  accounts survive destroying the `db` pod. Reachable only in-cluster so far; 3.7 adds the
  public route.
- [x] 3.4 Get images onto the node — direct import (`docker save | gzip | ssh | k3s ctr images
  import`) rather than standing up a registry; that becomes necessary in 3.8 when CI needs it.
  The `arm64` half was free: the dev machine is Apple Silicon, so `docker compose build` already
  produces `linux/arm64`. Images land in containerd's `k8s.io` namespace as
  `docker.io/library/feedme-{api,worker,ui}:latest`, which is what `imagePullPolicy: IfNotPresent`
  resolves against.
- [x] 3.5 Kubernetes manifests — Deployment/Service for db, redis, api, worker, ui; PVC for
  Postgres (see [ADR-0018](adr/0018-kubernetes-manifest-shape.md)). Written in `k8s/`, rendered
  and cross-checked offline; first apply against a real API server happens with 3.3.
- [x] 3.6 Secrets as Kubernetes Secrets — `feedme-secrets` in the `feedme` namespace, created
  imperatively so values never touch a file (see `k8s/secrets.example.yaml`). Postgres password,
  JWT secret and registration code are freshly generated for production rather than copied from
  the dev `.env`; only `ANTHROPIC_API_KEY` carries over.
- [x] 3.7 Domain + Ingress + TLS — `feedmepls.xyz` (Porkbun) and `www`, both A records at the
  node's now-reserved IP. cert-manager v1.21.2 issues from Let's Encrypt production after
  proving the flow against staging; Traefik terminates TLS and 301s HTTP to HTTPS. Verified
  from the public internet (`ssl_verify_result=0`) and by logging into the live site in a
  browser. See [ADR-0020](adr/0020-public-exposure-and-tls.md).
- [ ] 3.8 GitHub Actions — build, push, deploy on merge to main. **Three decisions open, not yet
  made** (raised 2026-09-24, deferred to the next session):
  - *Registry.* A CI runner can't `docker save | ssh` the way 3.4 does. GHCR is the likely answer —
    free for public repos and authenticates from Actions with the built-in `GITHUB_TOKEN`, no extra
    secret. Once images come from a registry, `imagePullPolicy: IfNotPresent` and the `:latest` tags
    in `k8s/` should become immutable per-commit tags (see [ADR-0018](adr/0018-kubernetes-manifest-shape.md)),
    so `kubectl rollout` can tell versions apart and roll back.
  - *How the runner reaches the cluster.* Port 6443 is deliberately closed to the internet
    ([ADR-0019](adr/0019-single-firewall-layer-on-the-node.md)). Either the runner SSHes to the node
    with a deploy key held as a GitHub secret and runs `kubectl` there, or 6443 opens to GitHub's
    published IP ranges. **Leaning SSH** — those ranges are broad and change, and opening the API
    server undoes a deliberate choice.
  - *Trigger.* Every push to `main`, or only tagged releases.
- [ ] Retire the `:latest` tags once 3.8 introduces real per-commit tags — noted in ADR-0018 as the
  point at which `imagePullPolicy: IfNotPresent` stops being needed.
- [ ] 3.9 Verify live — real domain, real TLS, all 50-user-scale checks passing

## Phase 4 — Multi-user + polish

- [x] Real multi-user auth (this is where [ADR-0002](adr/0002-user-id-scoping-from-day-one.md) pays off) —
  username/password + JWT, replacing the single-shared-token scheme from
  [ADR-0014](adr/0014-single-shared-token-auth.md); registration gated by a shared invite code for
  a bounded (~50 user) rollout (see [ADR-0015](adr/0015-jwt-multi-user-auth.md)). Verified live:
  register/log in/log out through the real Streamlit UI, two accounts confirmed data-isolated, wrong
  password rejected, pre-existing account retained its recipes after getting a real password.
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
