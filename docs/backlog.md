# FeedMe — Backlog

A running list of follow-ups noticed along the way that aren't part of the current phase's scope.
Unlike [roadmap.md](roadmap.md) (the structured, phased plan), this is unordered — just a place to
not lose track of things. When an item's time comes, either fold it into the roadmap as a real
phase item, or knock it out directly and remove it from here.

Each entry: what it is, why it matters, and where it came from (so it doesn't rot into a mystery
bullet point six months from now).

---

- [ ] **Node disk grows with every deploy.** Each release adds per-commit image tags to containerd.
  Partly addressed 2026-09-27: kubelet image GC tightened from 85/80 to 70/55 and a
  `FeedmeNodeDiskFilling` alert added (see [ADR-0025](adr/0025-monitoring-and-alerting.md)), because
  `local-path` puts the Postgres PVC on the same root filesystem — a full disk is data loss, not a
  failed pull. Image growth itself addressed 2026-10-02: `deploy.yml` now runs
  `k3s crictl rmi --prune` on the node after each successful deploy, so manual pruning is no longer
  needed. What remains is the shared disk — anything that fills it (Prometheus TSDB, logs) still
  threatens Postgres, and the real fix is giving Postgres its own block volume.
  *Noted: 2026-09-27, during Phase 3.9.*

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
