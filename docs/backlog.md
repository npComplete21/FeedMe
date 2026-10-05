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
