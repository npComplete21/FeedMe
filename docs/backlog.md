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

- [ ] **`POST /recipes/ingest` doesn't dedupe.** The Save page now remembers the task it is
  polling, disables Save until it resolves, and gives up after two minutes with "still working -
  check the Recipes tab" (fixed 2026-10-30; the poll loop used to have no timeout, and a tap
  mid-poll could lose the result or post twice). What remains: after that deadline the worker may
  still finish, and a user who taps Save again on the same link gets a second copy of the recipe.
  A server-side guard (same user + same URL within a few minutes returns the existing task or
  recipe) would close it. *Noted: 2026-10-30, during Phase 5.*

- [ ] **Pantry: Enter doesn't search, and "No matches." is unreachable.** The ingredient box is a
  plain `st.text_input`, so pressing Enter only commits the value - the user has to tap Find recipes;
  wrapping it in `st.form` fixes that. Separately, `POST /match` returns *every* recipe ranked,
  including 0% matches, so with a non-empty library the "No matches." state never shows (a nonsense
  pantry lists every recipe at 0%). Consider filtering `match_ratio > 0` in the page. *Noted:
  2026-10-30, during Phase 5.*

- [ ] **The tab-bar CSS depends on Streamlit internal test ids.** `app/ui/nav.py` targets
  `stHeader`, `stMainBlockContainer`, `stBottomBlockContainer`, `stPageLink-NavLink` and others, which
  are not a public API and can be renamed by an upgrade; `AppTest` cannot see CSS so nothing catches
  it (see [ADR-0032](adr/0032-mobile-first-ui-on-streamlit.md)). For now the `ui` extra is pinned to
  the tested range, `streamlit>=1.59.2,<1.60` (unpinned, the image resolved 1.66.1 on 2026-10-30,
  where only the login page and the Recipes tab were eyeballed), so an upgrade is a deliberate pin
  bump plus the live phone-width check. Still worth having: a Playwright/browser smoke check of the
  bar, the Ask input and the recipe rows at phone width, so bumping the pin isn't a manual pass.
  *Noted: 2026-10-30, during Phase 5.*
