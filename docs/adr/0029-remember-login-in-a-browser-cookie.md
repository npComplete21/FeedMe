# ADR 0029: Remember the login in a browser cookie written by the UI

Status: Accepted

## Context

The JWT from `/auth/login` ([ADR-0015](0015-jwt-multi-user-auth.md)) is valid for
`JWT_EXPIRATION_DAYS` (14), but the Streamlit UI kept it only in `st.session_state`, which lives
as long as one browser tab's websocket connection. Closing the tab, or a UI pod restart, meant
logging in again - the token was still valid, the UI had just forgotten it.

The fix is to keep the token in the browser. The constraint is Streamlit itself:

- It can **read** the request's cookies (`st.context.cookies`), but only as a snapshot taken when
  the tab connected.
- It has **no API to set a cookie**, and the UI talks to the API server-side (httpx from the
  Streamlit process), so the API can't set one on the browser either. An `HttpOnly` cookie would
  need a custom route on the Streamlit server, which it doesn't support cleanly.
- `localStorage` can only be read back via JavaScript in a component, which needs another round
  trip before the first render and a third-party component package.

## Decision

- **A `feedme_token` cookie, written by a one-line script** that the UI renders with
  `st.html(..., unsafe_allow_javascript=True)` on the run after a login: `Path=/`,
  `SameSite=Strict`, `Secure` when served over HTTPS, and `Max-Age` equal to the time left on the
  JWT's own `exp`, so the cookie can never outlive the token.
- **Restore on a fresh session:** if there is no token in session state, read the cookie and call
  a new **`GET /auth/me`**, which both validates the token and returns the email the header shows
  (the JWT carries only the user id). 200 restores the session; 401 (expired, rotated secret,
  deleted account) clears the cookie and shows the login screen; the API being unreachable shows
  the login screen but keeps the cookie for next time.
- **Logout, and any 401 mid-session, expire the cookie** (`Max-Age=0`) and set a session flag to
  ignore the stale `st.context.cookies` snapshot, which would otherwise log the tab straight back
  in.

Verified in a real browser: login sets the cookie (14 days, `SameSite=Strict`); a new tab is
logged in without the form; logout clears it and a new tab shows the login screen; a garbage
cookie is rejected and removed; a different browser is not logged in.

## Consequences

- Gain: one login per browser per 14 days instead of one per tab, with no new dependency.
- Cost: the cookie is readable by JavaScript (not `HttpOnly`), so an XSS bug in the UI could read
  the token. Mitigated by what the UI renders: recipe text, captions and chat replies go through
  Streamlit's markdown, which escapes HTML; the only `unsafe_allow_*` content is the fixed cookie
  script and the cuisine-grid CSS, neither of which interpolates user content (the token is
  JSON-escaped into the script). Any future `unsafe_allow_html` on user content would turn this
  into a token leak - don't add one.
- Cost: there is no "don't remember me" option - on a shared computer, use Log out. Rotating
  `JWT_SECRET_KEY` remains the "log everyone out" switch; remembered cookies then fail `/auth/me`
  and are cleared on the next visit.
- `GET /auth/me` is a new authenticated endpoint (still everything except `/health`,
  `/auth/register`, `/auth/login` requires a token).
