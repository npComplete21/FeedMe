# ADR 0015: Real multi-user auth — password + JWT, invite-code registration

Status: Accepted

## Context

[ADR-0014](0014-single-shared-token-auth.md) closed off the API with one static bearer token, but
explicitly deferred real accounts: everyone who held the token still resolved to the same
hardcoded `you@feedme.local` user. The actual goal driving Phase 4 — "I want 50 users to have 50
different logins" — needs distinct identities with isolated data, not just a closed door. This
also meant pulling Phase 4's auth item forward ahead of Phase 3 (AWS/k8s), since the hosting
decision was stalled on an open cost question (k3s vs EKS) and auth doesn't depend on it.

## Decision

**Username (email) + password, exchanged for a JWT.** Login is the one point that's genuinely
server/DB-backed — `POST /auth/login` checks the submitted password against the stored bcrypt hash.
Every request after that verifies the JWT's signature locally (`app/api/auth.py`,
`decode_access_token`) with no DB lookup: the token is self-describing (`user_id` + `exp` baked into
the signed payload), not a reference to server-side session state. This is the standard stateless-vs-
stateful tradeoff — chosen here because it needs zero new infrastructure (no session store), at the
cost of no instant revocation short of rotating `JWT_SECRET_KEY` (which invalidates every outstanding
login, not just one).

**bcrypt for password hashing** (`hash_password`/`verify_password`), industry-standard, salts
automatically, deliberately slow to resist brute-force.

**14-day expiration** (`JWT_EXPIRATION_DAYS`, default 14), a middle ground for a personal app used by
~50 known people — long enough that people aren't re-logging-in constantly, short enough that a
leaked token doesn't stay valid indefinitely. Configurable via `.env` without a code change.

**Registration gated by one shared invite code** (`FEEDME_REGISTRATION_CODE`), not open self-service
signup and not admin-created accounts. Proportionate to "hand this out to ~50 people I know" — no
email verification flow, no admin UI, just a shared secret required alongside email+password on
`POST /auth/register`. Checked with a plain equality comparison (not `secrets.compare_digest`) since,
unlike a bearer token that gates every request, this is a one-time check on an already-rate-limited-
by-human-effort registration form — the timing-attack surface is negligible here.

**`get_current_user_id` does verification and identity resolution in one step.** Under ADR-0014,
`require_auth_token()` (yes/no gate) and `get_current_user_id()` (always returns the one hardcoded
user) were separate functions on purpose, anticipating this exact seam. Now that the token itself
encodes identity, they collapse into one dependency (`app/api/deps.py`) — decoding the JWT *is* both
the auth check and the identity lookup, nothing left to separate.

**`password_hash` is a nullable column**, not a data migration. The pre-existing
`you@feedme.local` row (6 real recipes from earlier phases) would otherwise have no valid password
and be locked out. Nullable keeps the migration (`migrations/versions/0005_add_password_hash_to_users.py`)
pure DDL, consistent with this project's migration style; a one-off script then set a real password
on that row directly, same as any other account.

**The Streamlit UI gets a real login/register screen** (`app/ui/streamlit_app.py`), replacing
ADR-0014's "trusted client, no login screen" — there are now actual distinct users to authenticate.
The JWT lives in `st.session_state`, attached to the `httpx.Client` at construction time each script
run (Streamlit reruns the whole script per interaction, so this is equivalent to "per request"). An
`httpx` response event hook watches every API call for a `401` and clears the session + reruns back
to the login screen on expiry, instead of hand-checking status codes at each of the UI's many call
sites individually — centralizes the one behavior ("token no longer works → show login again")
regardless of which endpoint tripped it.

## Consequences

- Gain: real per-user data isolation — verified live (register two accounts through the actual
  running UI, confirmed each sees only their own recipes; wrong password rejected; the pre-existing
  account keeps its 6 recipes after getting a real password).
- Gain: no new infrastructure — JWT verification needs no session store, no Redis dependency beyond
  what Celery already uses it for.
- Cost: no instant single-user revocation. Compromised token → wait out `JWT_EXPIRATION_DAYS`, or
  rotate `JWT_SECRET_KEY` and log *everyone* out. Acceptable at this scale; would need a real
  revocation story (token blocklist, shorter-lived tokens + refresh tokens) at a bigger scale.
- Cost: `ingest_status` (`GET /recipes/ingest/{task_id}`) still doesn't scope by `user_id` — a
  pre-existing gap from Phase 2.2 (Celery task IDs aren't tied to the requesting user), now more
  pointed with real distinct accounts. Tracked in [docs/backlog.md](../backlog.md).
- Revisit when: Phase 3 puts this on the open internet — `FEEDME_REGISTRATION_CODE` as a single
  shared secret (rather than per-invite, revocable codes) is fine for a closed ~50-person rollout
  handed out by hand, not for a public-facing signup flow.
