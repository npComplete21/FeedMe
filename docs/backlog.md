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

- [ ] **Remove the test accounts before inviting real users.** `smoke@test.local` and
  `dana@feedmepls.xyz` were created during Phase 3 verification and hold throwaway recipes. Harmless,
  but they'll look odd in any future user count and the passwords were chosen for convenience, not
  secrecy. *Noted: 2026-09-27, during Phase 3.9.*

- [ ] **No alerting on silent failures.** Two known ones: the backup PAR will eventually expire and
  uploads stop while every pod stays green (ADR-0023), and cert-manager renewal failures surface only
  in `kubectl describe certificate`. Neither is visible without going to look. A single weekly check —
  or a cron that pings a healthcheck service on success — would cover both.
  *Noted: 2026-09-27, during Phase 3.9.*

- [ ] **Node disk grows with every deploy.** Each release adds per-commit image tags to containerd;
  pruning superseded images during 3.9 recovered ~1GB of a 30GB disk then at 53%. kubelet's image GC
  only triggers at 85%, so it self-manages before filling, but worth a periodic
  `k3s ctr -n k8s.io images ls` and prune, or tightening the GC threshold.
  *Noted: 2026-09-27, during Phase 3.9.*
