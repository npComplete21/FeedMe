"""Login gate, log in/out, and the remembered-login cookie (ADR-0029).

Moved unchanged in behaviour from the old single-script UI.
"""

import base64
import json
import time

import httpx
import streamlit as st

from app.ui import api

# Remembering a login across closed tabs (ADR-0029). The JWT is kept in a
# browser cookie; Streamlit can read cookies (st.context.cookies) but has no API
# to write one, so writes go through a tiny script on the next page render.
TOKEN_COOKIE = "feedme_token"


def _init_state() -> None:
    if "access_token" not in st.session_state:
        st.session_state.access_token = None
    if "user_email" not in st.session_state:
        st.session_state.user_email = None
    if "pending_cookie_script" not in st.session_state:
        st.session_state.pending_cookie_script = None
    # st.context.cookies is a snapshot from when this tab connected, so after a
    # logout it still holds the old token - without this flag the session would
    # immediately log itself back in from that stale snapshot.
    if "ignore_remembered_token" not in st.session_state:
        st.session_state.ignore_remembered_token = False


def _token_seconds_left(token: str) -> int:
    """Seconds until the JWT's own `exp`, so the cookie never outlives the token.
    Read without verifying the signature - the API verifies; this is only a TTL."""
    try:
        segment = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
        return max(0, int(claims["exp"] - time.time()))
    except (IndexError, KeyError, TypeError, ValueError):
        return 0


def _cookie_script(value: str, max_age: int) -> str:
    # json.dumps quotes and escapes the value for the JS string literal.
    return (
        "<script>document.cookie = "
        f"{json.dumps(TOKEN_COOKIE)} + '=' + {json.dumps(value)} + "
        f"'; Max-Age={max_age}; Path=/; SameSite=Strict' + "
        "(location.protocol === 'https:' ? '; Secure' : '');</script>"
    )


def _log_in(token: str, email: str) -> None:
    st.session_state.access_token = token
    st.session_state.user_email = email
    st.session_state.ignore_remembered_token = False
    st.session_state.pending_cookie_script = _cookie_script(token, _token_seconds_left(token))


def log_out() -> None:
    _init_state()
    st.session_state.access_token = None
    st.session_state.user_email = None
    st.session_state.ignore_remembered_token = True
    st.session_state.pending_cookie_script = _cookie_script("", 0)


def _restore_remembered_login() -> None:
    if st.session_state.access_token or st.session_state.ignore_remembered_token:
        return
    token = st.context.cookies.get(TOKEN_COOKIE)
    if not token:
        return
    try:
        response = httpx.get(
            f"{api.API_BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.HTTPError:
        return  # API unreachable - show the login screen, keep the cookie for next time
    if response.status_code == 200:
        st.session_state.access_token = token
        st.session_state.user_email = response.json()["email"]
    elif response.status_code == 401:
        log_out()  # expired or revoked - drop the cookie too


def _show_login_screen() -> None:
    st.title("FeedMe")
    login_tab, register_tab = st.tabs(["Log in", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in"):
                try:
                    response = httpx.post(
                        f"{api.API_BASE_URL}/auth/login",
                        json={"email": email, "password": password},
                        timeout=30,
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    st.error(api.error_detail(exc))
                except httpx.HTTPError as exc:
                    st.error(f"Request failed: {exc}")
                else:
                    _log_in(response.json()["access_token"], email)
                    st.rerun()

    with register_tab:
        with st.form("register_form"):
            email = st.text_input("Email", key="register_email")
            password = st.text_input("Password", type="password", key="register_password")
            registration_code = st.text_input("Registration code")
            if st.form_submit_button("Register"):
                try:
                    response = httpx.post(
                        f"{api.API_BASE_URL}/auth/register",
                        json={
                            "email": email,
                            "password": password,
                            "registration_code": registration_code,
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    st.error(api.error_detail(exc))
                except httpx.HTTPError as exc:
                    st.error(f"Request failed: {exc}")
                else:
                    _log_in(response.json()["access_token"], email)
                    st.rerun()


def require_login() -> None:
    """Return only when there is a logged-in user; otherwise show the login screen and stop."""
    _init_state()
    _restore_remembered_login()
    if st.session_state.pending_cookie_script:
        # Emitted on a run that doesn't immediately st.rerun(), so it reaches the browser.
        st.html(st.session_state.pending_cookie_script, unsafe_allow_javascript=True)
        st.session_state.pending_cookie_script = None

    if not st.session_state.access_token:
        _show_login_screen()
        st.stop()
