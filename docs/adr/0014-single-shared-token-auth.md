# ADR 0014: A single shared bearer token, not real user accounts

Status: Accepted

## Context

Every endpoint was completely open - `get_current_user_id()` (`app/api/deps.py`) silently resolved
to one hardcoded user with no credential check at all. Anyone who could reach the API had full
access. The roadmap calls this out explicitly as "starts single-user-token, designed to extend to
real multi-user auth" - real multi-user auth (registration, login, per-user sessions) is its own,
later Phase 4 item. This step's job is narrower: stop the API being wide open, without building the
user-account system Phase 4 will actually need.

## Decision

**One static secret, `FEEDME_API_TOKEN`**, generated once (`secrets.token_hex(32)`) and stored in
`.env` - same pattern as `ANTHROPIC_API_KEY` already is. It does not identify *which* user is
calling (there's still only the one hardcoded user); it's a pure access gate, not an identity system.

**Sent as `Authorization: Bearer <token>`**, not a custom header or query parameter - the standard
convention, and the natural thing to evolve into real per-user tokens later without changing shape.
Enforced via FastAPI's `HTTPBearer` security scheme + a `require_auth_token()` dependency
(`app/api/deps.py`) using `secrets.compare_digest()` for the comparison (avoids a timing side-channel
on the token check, cheap to do right).

**Applied once, at the router level** - `APIRouter(dependencies=[Depends(require_auth_token)])` in
`app/api/routes.py` - rather than added to each endpoint individually, so a route added later can't
accidentally ship unauthenticated by omission.

**`/health` deliberately stays outside the gate.** It's defined directly on the `FastAPI` app in
`app/main.py`, not on the protected router, so container health checks / uptime monitors don't need
the secret just to confirm the process is alive - a standard convention for liveness probes.

**Fails fast, not silently open.** `app/api/deps.py` reads `FEEDME_API_TOKEN` at import time and
raises `RuntimeError` immediately if it's missing, rather than either running unprotected or failing
confusingly on the first real request. The Streamlit UI does the equivalent with `st.error()` +
`st.stop()`. This required calling `load_dotenv()` from within `deps.py` itself, not just relying on
`app/main.py` having already called it - tests import `app.api.deps` directly (via
`tests/api/conftest.py`), before `app.main` would otherwise trigger that side effect, and the fail-fast
check needs the real value to check against regardless of which module gets imported first.

**The UI is a trusted client, not a login screen.** `app/ui/streamlit_app.py` reads the same
`FEEDME_API_TOKEN` from its own environment and attaches it to every request automatically - no
prompt, no session. It already knows `FEEDME_API_URL` the same way; this is one more piece of trusted
configuration, not a new UX surface. A real login screen is explicitly Phase 4's problem once there
are actual distinct users to authenticate.

**The `ui` container gets only `FEEDME_API_TOKEN`, not the whole `.env`.** `api` and `worker` use
`env_file: .env` (they need `ANTHROPIC_API_KEY` too), but `ui` has no use for that key, so it's passed
the one variable it needs via Compose's `${FEEDME_API_TOKEN}` substitution instead of a blanket
`env_file:` - least exposure, not just least dependency footprint (that's what ADR-0012 was about;
this is the same instinct applied to secrets instead of packages).

## Consequences

- Gain: the API is no longer open to anyone who can reach it. Verified live: `curl` without a token
  (or with a wrong one) gets `401` on every protected route, `/health` stays `200` regardless, and the
  Streamlit UI works exactly as before because it transparently supplies the token on every call.
- Gain: no DB migration, no password hashing, no session store - this is a pure environment-variable
  check, proportionate to what "single-user-token" actually asks for.
- Cost: this is *not* multi-user auth and shouldn't be mistaken for progress toward it beyond the
  transport mechanism (Bearer headers) staying the same. `get_current_user_id()` is unchanged - still
  one hardcoded user regardless of who holds the token.
- Cost: rotating the token means updating `.env` and restarting both `api` and `ui` - fine for a
  single deployment, would need a real secrets-rotation story before Phase 3 puts this on the internet
  for real.
- Revisit when: Phase 4 introduces real accounts - at that point the token stops being a blunt
  yes/no gate and becomes (or is replaced by) something that actually resolves to a specific user,
  which is exactly the seam `require_auth_token()` / `get_current_user_id()` being separate functions
  today is meant to make easy.
