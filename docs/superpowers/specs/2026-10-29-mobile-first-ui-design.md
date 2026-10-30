# Mobile-first UI redesign — design

Status: draft, awaiting approval · 2026-10-29

## Intent and why

Today the whole UI is one 560-line Streamlit script: five sections stacked in one scroll (Add a recipe,
What can I make?, Ask, Your recipes with filters, and each recipe's edit form inside its expander).
Two problems follow:

1. **Nothing says where to go.** Saving a recipe, browsing by cuisine, matching a pantry and chatting
   are four different ways to "do something with recipes", and they look like one page. The thing
   used most (browsing the library) sits at the bottom, under three tools.
2. **It isn't built for a phone, which is where this will mostly be used.** Recipes are saved from a
   phone (a Short or Reel you just watched), and cooked from a phone in a kitchen.

The user's own last session: they opened FeedMe, pasted a YouTube Short link, and wanted to save it.
They also expect that "look up a recipe" will often be the first thing they do. **Both must be one
tap away, always.**

The goal is a web app that is intuitive on a phone. It is not a native app.

## Decisions (the user's)

- **Layout: phone-app style.** A bottom tab bar with a prominent ＋ in the centre. (They first chose a
  two-doors landing page, then dropped it once they realised most use will be on phones.)
- **Stay on Streamlit.** No new frontend stack, no PWA yet. The share-sheet / PWA item stays on the
  roadmap as a separate, later decision.
- **Find a recipe** = search bar at the top, then a breakdown by cuisine; tap a cuisine to get its
  list. **Ordered by the user's own star ratings** (already built, ADR-0028). They considered "most
  opened" and dropped it, so there is no new tracking.
- Recipes is the home screen. Save is reachable from every screen.

## Goals

- Every top-level action has an obvious, labelled place, visible without scrolling.
- Comfortable one-handed use at ~390px width: single column, large tap targets, nothing that needs
  horizontal scrolling.
- Saving a recipe from a pasted link is the shortest path in the app.
- Reading a recipe while cooking is clean (no edit form in the way).
- No backend schema change, no migration, no new endpoint required.

## Non-goals

- Native app, PWA, share-sheet capture, offline mode.
- New features: photos, "cooked this", grocery list, meal plan, scaling, timers. This design leaves
  room for them (see "Later") but builds none of them.
- "Most opened" ranking or any usage tracking.
- Restyling the colours/branding beyond what mobile layout needs.

## Anti-goals (failure even if it technically works)

- It looks fine on a laptop and is awkward on a phone.
- A tab bar that vanishes, jumps or overlaps content on some screens, or breaks on a Streamlit update.
- Losing something that works today: the paste-the-text fallback when fetching fails, async ingest
  polling, login persistence across tabs (ADR-0029), editing a recipe, ratings, the cuisine boxes.
- A dead tab for a feature that doesn't exist yet.

## Information architecture

Bottom tab bar, four items, left to right:

| Tab | Purpose |
|---|---|
| **Recipes** (home) | Search bar on top. Below it the cuisine boxes with counts (the existing 3-up grid, now 2-up on a phone). Tapping one opens that cuisine's list. Typing in the search bar replaces the boxes with matching results. |
| **Pantry** | "I have X, Y, Z" → ranked matches (the existing `/match`). Becomes its own tab. |
| **＋** (centre, emphasised) | Save a recipe: paste a link, tap Save. |
| **Ask** | The chat, as it is today. |

Recipe lists, from either the cuisine tap or a search, are ordered by **Highest rated** by default,
with a "Sort by" switch (Highest rated / Newest). Unrated recipes come after rated ones.

A recipe opens on its own **recipe page**: title, tags, rating, ingredients, steps, source link. Edit
is behind an "Edit" button, not an always-open form under the steps. Back returns to the list the
user came from.

## Screen notes

- **Save (＋).** The "Source" radio goes away: the platform is detected from the URL
  (youtube.com / youtu.be → youtube, instagram.com → instagram, anything else → website). There is
  no override control: an unrecognised domain is simply treated as a website, which is also what
  the fallback path expects. The detected source is shown ("YouTube link") so the user can see it.
  The paste-text fallback stays and still opens automatically with the reason when a fetch fails.
  While ingest runs the page shows progress; on success it shows "Added: <title>" with an
  "Open recipe" action.
- **Pantry.** Same behaviour as today. The ingredients the user types are remembered for the session
  so going to a recipe and back doesn't lose them.
- **Ask.** Behaviour unchanged. Chat input must not collide with the tab bar.
- **Account.** Email display and Log out move out of the top of every page into a small account
  control (top-right). Login/register screen stays as is, shown before any tabs.

## Constraints

- Streamlit ≥ 1.50 (already pinned). Navigation through `st.navigation` with the built-in nav
  hidden, and our own bottom bar built from `st.page_link` inside a keyed container, fixed to the
  bottom with CSS. The code already styles Streamlit through `.st-key-<name>` selectors
  (cuisine grid), so this is an extension of an existing technique, not a new one.
- The UI stays a thin HTTP client of the API with no backend imports (ADR-0004).
- Unit-testable logic (platform detection, search filtering, ordering) lives in plain functions in
  `app/ui/`, tested with pytest. Pages are exercised with Streamlit's `AppTest` where practical and
  then checked live in a real browser at phone width (per CLAUDE.md), because CSS positioning can't
  be asserted by AppTest.

## My calls (the user hasn't seen these; flag any you disagree with)

1. **Search is client-side.** The UI already fetches the user's whole recipe list for the cuisine
   counts, so title/ingredient search filters that list in Python. No `q=` parameter on the API.
   Revisit if a user ever has thousands of recipes.
2. **No single-recipe endpoint.** The recipe page reads from the already-fetched list and is
   addressed by `?recipe=<id>` in the URL so it survives a refresh and a shared link. Add
   `GET /recipes/{id}` only if this proves awkward.
3. **Four tabs, no Plan tab** until the meal planner exists.
4. **Code shape.** Split `streamlit_app.py` into an entry file (auth, nav, tab bar) and one file per
   page under `app/ui/pages/`, with shared helpers (`client`, `_error_detail`, auth) in a small
   module. The 560-line monolith goes away.
5. **Delivery as small, individually committed steps**, each live-checked before the next:
   shell (nav + tab bar + mobile CSS + auth) → Recipes tab (search, cuisines, lists, ordering) →
   recipe page + edit → Save → Pantry → Ask → remove the old script. Each is a roadmap subphase
   with its own commit and push.
6. **ADR.** Record this as ADR-0032 (mobile-first UI on Streamlit); note that it narrows the
   "replace Streamlit around Phase 3–4" revisit trigger in ADR-0004 rather than overturning it.

## Left to the builder

- Exact breakpoints, spacing, tap-target sizes, and the tab-bar icons.
- How the recipe page is reached (page vs. view within the Recipes page) as long as Back works and
  the URL carries the recipe id.
- Empty states and copy ("No recipes yet — tap ＋ to save your first one").
- How the account control is built (popover vs. menu).

## Later (not in scope, but don't box it in)

A Plan tab; a grocery list fed from Pantry's missing ingredients; "cooked this" and photos on the
recipe page; a PWA + share-sheet capture, which is where the Streamlit-vs-real-frontend decision
gets revisited.
