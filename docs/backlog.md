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
  threatens Postgres, and the real fix is giving Postgres its own block volume — written up as a
  step-by-step [runbook](runbooks/postgres-own-block-volume.md), needs OCI console + node access to run.
  *Noted: 2026-09-27, during Phase 3.9.*

- [ ] **Save page: the ingest poll loop has no timeout.** `app/ui/views/save.py` polls
  `GET /recipes/ingest/{task_id}` until it resolves, and Celery reports a lost or expired task as
  `PENDING` forever, so if the worker is down a phone user waits indefinitely on a spinner. Needs an
  overall cap (a minute or two) and a "taking longer than expected - try again or paste the text"
  message. *Noted: 2026-10-30, during Phase 5.*

- [ ] **Pantry: Enter doesn't search, and "No matches." is unreachable.** The ingredient box is a
  plain `st.text_input`, so pressing Enter only commits the value - the user has to tap Find recipes;
  wrapping it in `st.form` fixes that. Separately, `POST /match` returns *every* recipe ranked,
  including 0% matches, so with a non-empty library the "No matches." state never shows (a nonsense
  pantry lists every recipe at 0%). Consider filtering `match_ratio > 0` in the page. *Noted:
  2026-10-30, during Phase 5.*

- [ ] **The tab-bar CSS depends on Streamlit internal test ids.** `app/ui/nav.py` targets
  `stHeader`, `stMainBlockContainer`, `stBottomBlockContainer`, `stPageLink-NavLink` and others, which
  are not a public API and can be renamed by an upgrade; `AppTest` cannot see CSS so nothing catches
  it (see [ADR-0032](adr/0032-mobile-first-ui-on-streamlit.md)). Consider a Playwright/browser smoke
  check of the bar at phone width, or an upper pin on `streamlit` in the `ui` extra. *Noted:
  2026-10-30, during Phase 5.*

- [ ] **Leaving the recipe page mid-edit leaves the edit flag set.** The per-recipe edit flag is
  never cleared when the user navigates away, so reopening that recipe in the same session lands in
  edit mode again (nothing is lost and Cancel works, but it's odd). Fix: clear the flag in
  `nav.open_recipe`. *Noted: 2026-10-30, during Phase 5.*
