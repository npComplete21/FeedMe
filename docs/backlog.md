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

- [ ] **Node disk grows with every deploy.** Each release adds per-commit image tags to containerd.
  Partly addressed 2026-09-27: kubelet image GC tightened from 85/80 to 70/55 and a
  `FeedmeNodeDiskFilling` alert added (see [ADR-0025](adr/0025-monitoring-and-alerting.md)), because
  `local-path` puts the Postgres PVC on the same root filesystem — a full disk is data loss, not a
  failed pull. Image growth itself addressed 2026-10-02: `deploy.yml` now runs
  `k3s crictl rmi --prune` on the node after each successful deploy, so manual pruning is no longer
  needed. What remains is the shared disk — anything that fills it (Prometheus TSDB, logs) still
  threatens Postgres, and the real fix is giving Postgres its own block volume.
  *Noted: 2026-09-27, during Phase 3.9.*

- [ ] **Let YouTube URLs accept a pasted transcript.** When YouTube's anti-bot check refuses a fetch
  (see ADR-0024), the user is told to paste the transcript — but the only manual path is the
  `instagram` source, so they have to mislabel a YouTube video as Instagram to use it. The backend
  already accepts `caption_text` for any non-YouTube platform; the change is to allow it for
  `youtube` too and show the caption box when a YouTube fetch fails, pre-filled with the URL.
  *Noted: 2026-09-27, while fixing the YouTube bot-check handling.*

- [ ] **Session doesn't survive closing the browser tab.** The JWT lives only in Streamlit's
  `st.session_state` (`app/ui/streamlit_app.py`), which is tied to the server-side session for that
  browser connection — there's no localStorage, cookie, or query-param persistence. Closing the tab
  (or a Streamlit process restart) forces re-login even though the JWT itself is still valid for
  `JWT_EXPIRATION_DAYS`. Fix would be persisting the token client-side (e.g. a cookie, or
  `localStorage` read back via a small JS/query-param bridge Streamlit doesn't support natively) so
  reopening the app in the same browser session picks the token back up instead of re-hitting the
  login gate. *Noted: 2026-09-27, requested as a future feature. Re-requested 2026-10-02.*

- [ ] **Browse recipes by cuisine as big boxes, not a filter dropdown.** Today cuisine is one of the
  filter controls in the recipe list (see [ADR-0009](adr/0009-tags-closed-vocabulary.md) for the
  closed vocabulary). Requested instead: a browse view with one large tappable box per cuisine
  (grid of cards), landing on that cuisine's recipes — filtering by *navigating*, not by
  dropdown-and-apply. Pure UI/UX work in `app/ui/streamlit_app.py`; no backend change expected,
  since the cuisine values already exist per-recipe. *Noted: 2026-10-02, requested as a future
  feature.*

- [ ] **Figure out if Instagram ingestion can work without copy-pasting the caption, or drop
  Instagram support entirely.** Today's Instagram path is manual-paste only (caption text + URL,
  see [ADR-0006](adr/0006-raw-source-staging-table.md)) — unlike YouTube, which auto-fetches via
  `yt-dlp` (modulo the anti-bot fallback in [ADR-0024](adr/0024-youtube-anti-bot-check.md)).
  Needs research: does `yt-dlp` or another approach support pulling an Instagram Reel's caption
  without a logged-in session or scraping that risks the account? If there's no clean automated
  path, the manual-paste-only flow may not be worth keeping as a distinct "platform" — consider
  removing Instagram as a source type rather than keeping a half-automated experience around.
  *Noted: 2026-10-02, requested as a future feature.*

- [ ] **Recipe ratings + a ranked, filterable retrieval surfaced through the chatbot.** Roadmap's
  Phase 4 already lists "Recipe photos, ratings, 'cooked this' tracking" as an unstarted item; this
  sharpens the ask: rate recipes, then be able to pull a ranked list filterable by ingredient and
  cuisine — and expose that as a chat tool (see [ADR-0011](adr/0011-chat-uses-tool-use-not-free-text-reasoning.md)
  for why chat already works via tool-use, not free-text reasoning over all recipes), so "give me my
  5 best chicken recipes" resolves to a real query (rating DESC, ingredient/cuisine filtered, limit
  5) rather than the model guessing from context. Needs a `rating` column (or a separate ratings
  table if multiple ratings per recipe ever matter), a matching API endpoint/query, and a new tool
  definition for the chat tool-use loop. *Noted: 2026-10-02, requested as a future feature.*
