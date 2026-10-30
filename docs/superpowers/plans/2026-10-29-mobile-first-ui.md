# Mobile-first UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-scroll Streamlit script with a phone-first, four-tab app (Recipes, Pantry, ＋ Save, Ask) plus a recipe page, with no backend change.

**Architecture:** `app/ui/streamlit_app.py` becomes a thin entry file: auth gate, hidden `st.navigation`, a fixed bottom tab bar, then `nav.run()`. Each screen is a file in `app/ui/views/`. Pure logic (URL→platform, search, counts, text parsing) lives in `app/ui/logic.py` and is unit-tested; shared plumbing lives in `app/ui/auth.py`, `app/ui/api.py`, `app/ui/nav.py`, `app/ui/components.py`.

**Tech Stack:** Streamlit ≥ 1.50 (1.59.2 installed), httpx, pytest + `streamlit.testing.v1.AppTest`.

**Spec:** [docs/superpowers/specs/2026-10-29-mobile-first-ui-design.md](../specs/2026-10-29-mobile-first-ui-design.md)

## Global Constraints

- Streamlit `>=1.50`; navigation via `st.navigation(..., position="hidden")` and our own bar built from `st.page_link` in `st.container(key="tab-bar")`, fixed to the bottom with CSS on `.st-key-tab-bar` (same `.st-key-<name>` technique the cuisine grid uses today).
- Four tabs, left to right: **Recipes**, **Pantry**, **＋** (Save), **Ask**. No Plan tab.
- Recipe lists default to **Highest rated** (`sort=rating`, unrated last, done by the API); alternative **Newest**. Cuisine ordering follows `CUISINES` in `app/ui/vocabulary.py`.
- The UI is a pure HTTP client: no imports from `app.api`, `app.persistence`, `app.parsing`, etc. (ADR-0004/0012).
- No backend change, no migration, no new endpoint. Search is client-side over the fetched recipe list. The recipe page is addressed by `?recipe=<id>`.
- Pages never call `st.set_page_config` (only the entry file does) and get the API client via `from app.ui import api` then `api.get_client()` (so tests can monkeypatch `app.ui.api.get_client`).
- Must keep: paste-text fallback that auto-opens with the reason on fetch failure, async ingest polling, cookie login persistence (ADR-0029), global 401 → login screen, rating, full-replace edit (ADR-0010).
- Phone target ~390px wide: single column, nothing scrolls horizontally.
- Entry file stays `app/ui/streamlit_app.py` so `docker/ui.Dockerfile` and `k8s/` need no change.
- Commit **and push** after each task (CLAUDE.md). Do not tag a release until Task 8.
- Test command (the worktree has no venv; the parent repo's imports the worktree's `app`): `/Users/yashpundlik/PycharmProjects/FeedMe/.venv/bin/python -m pytest tests/ui -q`. Live checks: start the stack per CLAUDE.md "Fast iteration", open `http://localhost:8501` in the Browser pane, `resize_window` preset `mobile`.

## Review Focus

1. A recipe with **no cuisine** must stay reachable (it has no cuisine box). → an "All recipes" box is always shown last; covered in Task 3.
2. `?recipe=<id>` for an id that isn't in the user's list (deleted, someone else's, garbage like `abc`) shows "Recipe not found" with a way back, never a traceback. → Task 4.
3. Save with a pasted value that is blank, has surrounding whitespace, lacks `https://`, or isn't a link at all. → Task 1 (`normalize_url`) and Task 5.
4. Search that is whitespace-only (acts as no search), upper-case, or matches nothing (explicit empty state, not a blank page). → Tasks 1 and 3.
5. An expired token mid-session lands on the login screen from any tab, and a fetch-failure fallback or pantry text survives switching tabs and back. → Tasks 2, 5, 6.

---

### Task 1: Pure UI logic

**Files:**
- Create: `app/ui/logic.py`
- Test: `tests/ui/test_logic.py`

**Interfaces:**
- Produces (all pure, no Streamlit import):
  - `Platform = Literal["youtube", "instagram", "website"]`
  - `normalize_url(raw: str) -> str | None`. Strips whitespace; prepends `https://` when no scheme; returns `None` if blank or the result has no dot-containing host or contains inner whitespace.
  - `detect_platform(url: str) -> Platform`. By hostname: `youtube.com`, `*.youtube.com`, `youtu.be` → youtube; `instagram.com`, `*.instagram.com` → instagram; anything else → website. Host match is exact-suffix on a dot boundary (`notyoutube.com` is website).
  - `search_recipes(recipes: list[dict], query: str) -> list[dict]`. Case-insensitive substring over title and ingredient names; blank/whitespace query returns the list unchanged; order preserved.
  - `cuisine_counts(recipes: list[dict]) -> dict[str, int]`. Only recipes with a truthy `cuisine`.
  - `cuisine_label(cuisine: str) -> str` (`"middle_eastern"` → `"Middle Eastern"`) and `recipe_tags(recipe: dict) -> list[str]` (cuisine label, meal-type label, `"<n> min"`, `"★" * rating`, in that order, each only if present).
  - `ingredients_to_text(ingredients: list[dict]) -> str` and `parse_ingredients_text(text: str) -> list[dict]` (moved verbatim from the old script: `name, quantity` per line), `parse_pantry(text: str) -> list[str]` (comma-split, stripped, empties dropped).

- [ ] **Step 1: Write failing tests** in `tests/ui/test_logic.py`, with at least:
  `test_detect_platform_youtube_variants` (`https://www.youtube.com/shorts/abc`, `https://youtu.be/abc`, `https://m.youtube.com/watch?v=1` → `"youtube"`), `test_detect_platform_instagram` (`https://www.instagram.com/reel/x/`), `test_detect_platform_lookalike_host_is_website` (`https://notyoutube.com/x`, `https://youtube.com.evil.io/x` → `"website"`), `test_normalize_url_adds_scheme_and_trims` (`"  youtu.be/abc "` → `"https://youtu.be/abc"`), `test_normalize_url_rejects_non_links` (`""`, `"   "`, `"chicken curry"`, `"hello"` → `None`), `test_search_matches_title_and_ingredient_case_insensitively`, `test_search_blank_query_returns_everything_in_order`, `test_search_no_match_returns_empty`, `test_cuisine_counts_skips_missing_cuisine`, `test_recipe_tags_order_and_omissions`, `test_parse_ingredients_roundtrip`, `test_parse_pantry_drops_blanks`.
- [ ] **Step 2: Run** `... pytest tests/ui/test_logic.py -q`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement** `app/ui/logic.py` per the Interfaces block. Use `urllib.parse.urlsplit` for hostnames.
- [ ] **Step 4: Run** `... pytest tests/ui -q`. Expected: PASS (including the existing vocabulary tests).
- [ ] **Step 5: Commit and push** — `git add app/ui/logic.py tests/ui/test_logic.py && git commit -m "Add pure UI logic for the mobile redesign" && git push`.

---

### Task 2: App shell — entry file, auth, API client, tab bar

**Files:**
- Create: `app/ui/auth.py`, `app/ui/api.py`, `app/ui/nav.py`, `app/ui/views/__init__.py`, and stub pages `app/ui/views/{recipes,pantry,save,ask,recipe}.py` (each just `st.write("<name> — coming next")`; real content arrives in Tasks 3–7)
- Modify: `app/ui/streamlit_app.py` (rewrite as the thin entry file), `docs/roadmap.md` (add "Phase 5 — Mobile-first UI" with subphases 5.1 shell, 5.2 Recipes tab, 5.3 Recipe page, 5.4 Save, 5.5 Pantry, 5.6 Ask, 5.7 cleanup + docs; this task ticks 5.1)
- Test: `tests/ui/test_shell.py`

**Interfaces:**
- Produces:
  - `auth.py`: move, unchanged in behaviour, the cookie/login code from the old script: `require_login() -> None` (restores remembered login, emits the pending cookie script, shows the Log in / Register tabs and `st.stop()`s when not logged in), `log_out() -> None`.
  - `api.py`: `get_client() -> httpx.Client` (base URL from `FEEDME_API_URL`, bearer header from `st.session_state.access_token`, response hook that calls `auth.log_out()` + `st.rerun()` on 401), `error_detail(exc: httpx.HTTPStatusError) -> str`.
  - `nav.py`: `render_header() -> None` (app name left; account `st.popover` right showing the email and a Log out button), `render_tab_bar() -> None`, `open_recipe(recipe_id: int) -> None` (sets `st.session_state.open_recipe_id`, then `st.switch_page("views/recipe.py")`).
  - Entry file order: `st.set_page_config(page_title="FeedMe", page_icon="🍳", layout="centered", initial_sidebar_state="collapsed")` → `auth.require_login()` → `st.navigation([...5 pages, Recipes default, recipe page with url_path="recipe"], position="hidden")` → inject mobile CSS → `render_header()` → `render_tab_bar()` → `page.run()`.

- [ ] **Step 1: Write failing tests** in `tests/ui/test_shell.py` using `AppTest.from_file("app/ui/streamlit_app.py")`: `test_logged_out_shows_login_not_tabs` (no `access_token` → a "Log in" tab/button exists and no tab-bar page links), `test_logged_in_renders_four_tabs` (set `at.session_state["access_token"]="t"`, `user_email`, monkeypatch `app.ui.api.get_client` to a stub whose `get` returns an empty list; assert page links labelled Recipes, Pantry, Save, Ask exist and none labelled Plan), `test_401_logs_out` (stub client whose hook-equivalent path calls `auth.log_out`; assert token cleared).
- [ ] **Step 2: Run** `... pytest tests/ui/test_shell.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the files above. Mobile CSS (one `st.markdown(..., unsafe_allow_html=True)` block in `nav.py`): `.st-key-tab-bar` fixed bottom, full width, `z-index` above content, safe-area inset padding; main block container bottom padding ≥ the bar height so the last item is never covered; larger min tap height for buttons; hide Streamlit's deploy/toolbar chrome. The ＋ tab is visually emphasised (filled circle).
- [ ] **Step 4: Run** `... pytest tests/ui -q`. Expected: PASS.
- [ ] **Step 5: Live check at phone width.** Start backend, db, redis per CLAUDE.md. Verify: login works; reload stays logged in; the bar stays fixed at the bottom while scrolling a long stub; tapping each tab switches page and highlights it; Log out in the popover returns to the login screen; no horizontal scroll.
- [ ] **Step 6: Commit and push** — "Mobile-first shell: hidden navigation and fixed bottom tab bar".

---

### Task 3: Recipes tab — search, cuisine boxes, lists

**Files:**
- Create: `app/ui/components.py`
- Modify: `app/ui/views/recipes.py`
- Test: `tests/ui/test_recipes_page.py`

**Interfaces:**
- Consumes: `logic.search_recipes`, `cuisine_counts`, `cuisine_label`, `recipe_tags`; `nav.open_recipe`; `api.get_client`.
- Produces: `components.recipe_row(recipe: dict, key_prefix: str) -> None` (one full-width tappable row: title, then tag line; tapping calls `nav.open_recipe(recipe["id"])`; keys unique per `key_prefix` + id). Session keys used by this page: `selected_cuisine: str | None` (`None` = boxes, `"__all__"` = everything) and `recipes_sort: "rating" | "newest"`.
- Page behaviour: search `st.text_input` on top (placeholder "Search recipes or ingredients"). Blank → cuisine boxes (2 per row on phone), ending with an **All recipes · N** box; a cuisine or All box shows that list with "← Back" and a **Sort by** control (Highest rated default, Newest). Non-blank query → results list of `search_recipes(...)` in the current sort, boxes hidden; zero results → "No recipes match “<query>”". Empty library → "No recipes yet — tap ＋ to save your first one". Fetch once per run with `params={"sort": ...}`; do not send cuisine to the API (same reasoning as today's script).

- [ ] **Step 1: Write failing tests** with `AppTest` and a stub client returning four recipes (two italian rated 5 and 3, one korean, one with `cuisine=None`): `test_boxes_show_counts_and_all_box` (boxes for Italian·2, Korean·1, and "All recipes · 4"), `test_uncategorised_recipe_reachable_via_all`, `test_search_replaces_boxes_and_filters` (typing `"KIMCHI"` hides boxes, shows only the matching row), `test_whitespace_search_is_ignored`, `test_search_no_match_shows_empty_state`, `test_empty_library_message`, `test_default_sort_param_is_rating` (stub records the `sort` param it received).
- [ ] **Step 2: Run** `... pytest tests/ui/test_recipes_page.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `components.recipe_row` and the page. Port the cuisine-box CSS and `CUISINE_EMOJI` from the old script (git history of `streamlit_app.py`); drop the old meal-type and max-cook-time filters from this screen (the spec's Recipes tab has search, boxes, sort only; note this in the commit message so the removal is a visible, reversible decision).
- [ ] **Step 4: Run** `... pytest tests/ui -q`. Expected: PASS.
- [ ] **Step 5: Live check at phone width** with several saved recipes: boxes 2-up, tap a cuisine, order matches ratings, switch to Newest, search by an ingredient, clear search returns to boxes, the last row is not hidden behind the tab bar.
- [ ] **Step 6: Commit and push**, tick 5.2 in the roadmap.

---

### Task 4: Recipe page — read, rate, edit

**Files:**
- Modify: `app/ui/views/recipe.py`
- Test: `tests/ui/test_recipe_page.py`

**Interfaces:**
- Consumes: `nav.open_recipe` (sets `open_recipe_id`), `logic.recipe_tags`, `ingredients_to_text`, `parse_ingredients_text`, `api.get_client`.
- Produces: page resolves the recipe id from `st.query_params["recipe"]` first, else `st.session_state.open_recipe_id`, then writes it back to `st.query_params["recipe"]` so a refresh or shared link works. Finds it in `GET /recipes`. Sections in order: title + tags, star rating (`st.feedback("stars")`, PUT `/recipes/{id}/rating`, as today), source link, Ingredients, Steps, then an **Edit** button. Edit mode (a session flag) shows the existing full-replace form (title, steps, ingredients, cuisine, meal type, cook time → PUT `/recipes/{id}`), Save and Cancel; saving returns to read mode. A "← Back to recipes" `st.page_link` returns to Recipes, whose `selected_cuisine`, sort and search text are still in session state.

- [ ] **Step 1: Write failing tests**: `test_renders_ingredients_and_steps_for_id_from_session`, `test_id_from_query_param_wins`, `test_unknown_id_shows_not_found_with_back_link`, `test_non_numeric_id_shows_not_found`, `test_edit_form_hidden_until_edit_pressed`, `test_save_sends_put_with_parsed_ingredients` (stub records the PUT payload; assert ingredients parsed from the textarea and `cuisine` `None` for "(none)").
- [ ] **Step 2: Run** `... pytest tests/ui/test_recipe_page.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the page, porting the rating and edit code from the old script.
- [ ] **Step 4: Run** `... pytest tests/ui -q`. Expected: PASS.
- [ ] **Step 5: Live check at phone width**: open from a cuisine list and from search, rate, refresh the browser (stays on the same recipe), edit and save, back keeps the list state, `?recipe=99999` shows not-found.
- [ ] **Step 6: Commit and push**, tick 5.3.

---

### Task 5: Save (＋)

**Files:**
- Modify: `app/ui/views/save.py`
- Test: `tests/ui/test_save_page.py`

**Interfaces:**
- Consumes: `logic.normalize_url`, `logic.detect_platform`, `nav.open_recipe`, `api.get_client`, `api.error_detail`.
- Page behaviour: a single URL input and a **Save recipe** button. Below the input, once the value normalises, show the detected source ("YouTube link" / "Instagram post" / "Website"). Invalid value → "That doesn't look like a link" and no request. Submit POSTs `/recipes/ingest` with `{"source_platform": detect_platform(url), "url": url}` (plus `caption_text` if the paste box is filled), then polls `/recipes/ingest/{task_id}` every 2s inside `st.status`, exactly as the old script. Success → "Added: <title>" and an **Open recipe** button calling `nav.open_recipe`. Failure on an automatic fetch stores `fetch_failure` `{platform, url, error}` in session state and reruns; the paste-text expander (copy per platform from the old `PASTE_COPY`) opens with the reason whenever the stored failure matches the current URL. State lives in `st.session_state`, so it survives switching tabs and back.

- [ ] **Step 1: Write failing tests**: `test_invalid_link_blocks_request` (stub records no POST), `test_detected_source_label_shown_for_shorts_url`, `test_ingest_payload_has_detected_platform_and_normalised_url`, `test_fetch_failure_opens_paste_box_with_reason`, `test_paste_text_included_in_payload`, `test_success_shows_open_recipe`.
- [ ] **Step 2: Run** `... pytest tests/ui/test_save_page.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**, porting polling and fallback code from the old script (git history).
- [ ] **Step 4: Run** `... pytest tests/ui -q`. Expected: PASS.
- [ ] **Step 5: Live check at phone width** with the worker running: paste a YouTube Short link without `https://`, save, open the result; force a failure (bad URL) and confirm the paste box opens with the reason and survives a tab switch.
- [ ] **Step 6: Commit and push**, tick 5.4.

---

### Task 6: Pantry tab

**Files:**
- Modify: `app/ui/views/pantry.py`
- Test: `tests/ui/test_pantry_page.py`

**Interfaces:**
- Consumes: `logic.parse_pantry`, `components.recipe_row`, `api.get_client`.
- Page behaviour: text input "What's in your kitchen? (comma-separated)" keyed `pantry_text` (persisted in session state) and a **Find recipes** button → POST `/match` with `{"pantry": parse_pantry(text)}`. Each result: title, match %, Have / Missing lists, and an **Open recipe** control (`nav.open_recipe`) instead of inline steps. Empty pantry → prompt, no request. No matches → "No matches."

- [ ] **Step 1: Write failing tests**: `test_blank_pantry_makes_no_request`, `test_pantry_payload_is_parsed_list`, `test_results_show_have_and_missing`, `test_no_matches_message`, `test_pantry_text_persists_in_session_state`.
- [ ] **Step 2: Run** `... pytest tests/ui/test_pantry_page.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**, porting from the old script.
- [ ] **Step 4: Run** `... pytest tests/ui -q`. Expected: PASS.
- [ ] **Step 5: Live check at phone width**: match, open a result, come back, the text and results are still there.
- [ ] **Step 6: Commit and push**, tick 5.5.

---

### Task 7: Ask tab

**Files:**
- Modify: `app/ui/views/ask.py`
- Test: `tests/ui/test_ask_page.py`

**Interfaces:**
- Consumes: `api.get_client`, `api.error_detail`. Keeps session keys `chat_history` (opaque provider history) and `chat_display` (`[(role, text)]`) from the old script.
- Page behaviour unchanged: render history, `st.chat_input`, POST `/chat` with `{"message", "history"}`, store the returned history, show errors inline. Add: a short empty-state hint and a "New chat" button that clears both keys. The chat input must sit above the tab bar, not under it (adjust `[data-testid="stBottom"]` offset in the shell CSS if needed).

- [ ] **Step 1: Write failing tests**: `test_chat_posts_message_with_history_and_appends_reply`, `test_chat_error_shown_inline_and_history_unchanged`, `test_new_chat_clears_state`.
- [ ] **Step 2: Run** `... pytest tests/ui/test_ask_page.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**, porting from the old script.
- [ ] **Step 4: Run** `... pytest tests/ui -q`. Expected: PASS.
- [ ] **Step 5: Live check at phone width** with the real Anthropic key: multi-turn chat; the input is fully visible above the tab bar; history survives a tab switch.
- [ ] **Step 6: Commit and push**, tick 5.6.

---

### Task 8: Cleanup, docs, full pass

**Files:**
- Modify: `docs/roadmap.md` (tick 5.7, mark Phase 5 complete only after the full pass), `CLAUDE.md` (Architecture section: UI is now an entry file plus `app/ui/views/`; keep the `streamlit run app/ui/streamlit_app.py` command unchanged), `docs/adr/0004-streamlit-for-phase-0-ui.md` (add a status note pointing to ADR-0032)
- Create: `docs/adr/0032-mobile-first-ui-on-streamlit.md` (template `docs/adr/template.md`: Context / Decision / Consequences, including why not a PWA/real frontend yet, the hidden-nav + CSS tab bar and its fragility, client-side search, `?recipe=` addressing, the removed meal-type/cook-time filters, and that PWA/share-sheet is the next revisit trigger)

- [ ] **Step 1: Confirm nothing dead remains**: `grep -rn "st.header(\"Add a recipe\")\|PASTE_COPY" app/ui` returns only `views/save.py`; the old single-script code is fully gone from `streamlit_app.py`.
- [ ] **Step 2: Full test run**: `/Users/yashpundlik/PycharmProjects/FeedMe/.venv/bin/python -m pytest -q`. Expected: PASS (whole suite, not just `tests/ui`).
- [ ] **Step 3: Containerised pass**: `docker compose up -d --build`, then at `resize_window` mobile walk the user's own scenario end to end: open → tap ＋ → paste a YouTube Short link → open the saved recipe → rate → Recipes → search it → Pantry → Ask. Also repeat at the tablet and desktop presets to confirm nothing breaks.
- [ ] **Step 4: Write ADR-0032 and the doc edits.**
- [ ] **Step 5: Commit and push**; tick 5.7 and mark Phase 5 complete. Releasing (tag `v*`) is the user's call.

---

## Self-review notes

- **Spec coverage:** four-tab bar (T2), Recipes search/boxes/rating-sort (T3), recipe page with Edit behind a button and `?recipe=` (T4), Save with platform detection and kept fallback (T5), Pantry tab (T6), Ask (T7), account control (T2), ADR-0032 + ADR-0004 note + "Later" untouched (T8), client-side search and no backend change (Global Constraints).
- **Beyond the spec, flagged for the user:** an always-present **All recipes** box (Review Focus 1: otherwise cuisine-less recipes would be unreachable except by search), and the meal-type / max-cook-time filters are dropped from the Recipes screen because the agreed design is search + cuisine + sort only. Either can be reversed cheaply.
