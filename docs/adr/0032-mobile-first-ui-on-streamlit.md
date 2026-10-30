# ADR 0032: A phone-first UI on Streamlit - hidden navigation and our own tab bar

Status: Accepted

## Context

The UI was one long Streamlit script (~560 lines): add a recipe, "what can I make?", the chat, the
recipe list and the edit form all stacked on one scroll. That is fine at a desk and awkward on a
phone, which is where most use happens - the recipes come from Instagram and YouTube, which people
browse on a phone, and the kitchen is where a recipe gets read. Two things were wanted at once: an
app that is comfortable one-handed at ~390px, and no new frontend stack to learn and host.
[ADR-0004](0004-streamlit-for-phase-0-ui.md) said to expect to replace Streamlit "around Phase 3-4"
once the UI stabilised; the question for Phase 5 was whether that time had come.

The design is in
[the Phase 5 spec](../superpowers/specs/2026-10-29-mobile-first-ui-design.md). The constraints that
mattered: no backend change, nothing that works today may be lost (the paste-the-text fallback,
async ingest polling, login across tabs, editing, ratings), and a tab bar that jumps or overlaps
content is a failure even if everything else works.

## Decision

**Phone-first, four tabs.** A bottom tab bar - Recipes, Pantry, a prominent centre ＋ Save, Ask -
plus a recipe page that is not a tab. Recipes is home; Save is one tap from everywhere. Each tab is
a thing a person does ("find a recipe", "what can I make", "save one", "ask"), which keeps the bar
to four. There is no Plan tab until a meal planner exists: a dead tab was an explicit anti-goal.

**Stay on Streamlit; no PWA or real frontend yet.** Everything the redesign needs is reachable from
Streamlit with CSS, and the app stays one Python toolchain. This narrows ADR-0004's revisit note
rather than overturning it: the trigger is now **the PWA / share-sheet work** (the roadmap's
"faster link capture" item). A share-sheet target needs a web app manifest and a service worker,
which Streamlit cannot serve; that is the point to build a real frontend (or a thin PWA shell), not
before.

**Pages in `app/ui/views/`, not `pages/`.** The entry file `streamlit_app.py` does page config,
`st.navigation`, the login gate and the shell; one file per screen lives in `app/ui/views/`
(`recipes`, `recipe`, `save`, `pantry`, `ask`), with `auth.py`, `api.py`, `nav.py`, `components.py`
and the pure `logic.py` beside it. The folder is deliberately not called `pages/`: Streamlit
auto-discovers a `pages/` folder next to the entry file and, on the first run after a server
restart, can run a page file directly (legacy folder navigation) without going through the entry
file, so the login gate and shell are skipped. `tests/ui/test_shell.py` has a guard test that
fails if a `pages/` folder appears.

**Streamlit's navigation is hidden; we draw the bar.** `st.navigation(..., position="hidden")`
still does the routing (URLs, `st.switch_page`, `st.page_link`); the bar is a row of
`st.page_link`s inside `st.container(key="tab-bar")`, pinned with CSS on the `.st-key-tab-bar` class
that a keyed container gets. Streamlit's built-in nav cannot be a fixed bottom bar with a raised
centre button; this can.

**Recipe search is client-side.** The Recipes tab already fetches the whole list to count cuisines,
so title/ingredient search filters it in Python (`logic.py`). No `q=` parameter, no backend change.

**The recipe page is addressed by `?recipe=<id>`.** The page reads the id from the query string
(the source of truth), falling back to session state, and finds the recipe in the list the app
already fetches - there is no single-recipe endpoint. A refresh or a shared link reopens the same
recipe. `st.switch_page` clears every query param it isn't given, so `nav.open_recipe` passes
`query_params={"recipe": ...}`. **`open_recipe` must run in the script body, never as a widget's
`on_click`**: inside a callback Streamlit turns `st.switch_page` into a no-op (it logs "Calling
st.rerun() within a callback is a no-op"), and only the query param changes. Callbacks may set
state; the navigation happens after, in the body (`if st.button(...): nav.open_recipe(id)`).

**Ordering is by the user's own ratings** (Highest rated by default, Newest as the alternative;
unrated last), reusing [ADR-0028](0028-recipe-ratings-and-ranked-retrieval.md).

**Removed: the meal-type and max-cook-time filters.** The agreed screen is search + cuisine boxes +
sort. An always-present "All recipes" box keeps cuisine-less recipes reachable. Both filters remain
in git history (`6d0abd0:app/ui/streamlit_app.py`) and are cheap to bring back if missed.

**No usage tracking.** "Most opened" ordering was considered and dropped, so nothing records which
recipes are opened.

## Consequences

- Gain: a phone-shaped app with no new toolchain, no backend change and no migration; the 560-line
  script is now a thin entry file plus small single-purpose modules, with the pure logic (platform
  detection, search, ordering) tested under plain pytest and the pages under `AppTest`.
- **Cost - the tab bar is the fragile part.** It styles Streamlit's internals, which are not a
  public API. The CSS in `app/ui/nav.py` relies on these test ids and DOM shapes:
  `header[data-testid="stHeader"]` (hidden), `stMainBlockContainer` (bottom padding so the bar
  never covers the last item), `stBottomBlockContainer` (the pinned `st.chat_input`, padded to
  clear the bar), `stPageLink` and `stPageLink-NavLink` (the tab links, restyled into columns),
  `stIconMaterial` (the ＋ circle), `stMarkdown`, `stElementContainer`, `stPopover`, and
  `stMarkdownContainer` inside recipe-row buttons, plus the `.st-key-<name>` classes from keyed
  containers. A Streamlit upgrade can rename any of them. **Re-check the bar, the Ask input and the
  recipe rows in a browser at phone width after every Streamlit upgrade.** `AppTest` cannot see
  CSS, so nothing automated catches a break; instead the `ui` extra is pinned to the tested range,
  `streamlit>=1.59.2,<1.60` (everything was verified on 1.59.2), and raising that pin is the
  upgrade that needs the live check. Unpinned, the image had resolved 1.66.1 on 2026-10-30, where
  only the login page and the Recipes tab were eyeballed. A browser smoke check that would let the
  pin move more freely is in the backlog.
- Cost: the bar's colours are hard-coded for light and dark (picked from `st.context.theme.type`),
  because Streamlit exposes no public CSS variables, and the page icons/titles are listed twice
  (the `st.Page` list and `nav.TABS`). Renaming a tab means editing both.
- Cost: shared modules (`nav.py`, `api.py`, `auth.py`, `logic.py`) are not hot-reloaded by
  `streamlit run` - restart the dev server after editing them. And under an editable install the
  worktree's UI can import another checkout's `app` package; set `PYTHONPATH` to the checkout.
- Cost: client-side search means the whole recipe list is fetched and filtered per run. Fine for
  hundreds of recipes; revisit (a `q=` parameter) if a user ever has thousands.
- Cost: no recipe is a first-class page on the server, so a shared `?recipe=<id>` link only works
  for its owner (all endpoints are user-scoped, [ADR-0002](0002-user-id-scoping-from-day-one.md)).
- Revisit: when the PWA / share-sheet work starts (above), or if the bar breaks on a Streamlit
  upgrade more than once.
