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

- [ ] **Block pod egress to the OCI metadata service (`169.254.169.254`).** Any process on the k3s
  node — including any container — can reach the instance metadata endpoint, which returns instance
  identity and, where configured, credentials. This is the standard SSRF-to-cloud-metadata exposure,
  and in a Kubernetes context a compromised pod is exactly the attacker that benefits. Not introduced
  by us (Oracle's shipped `OUTPUT` rules already ACCEPTed `169.254.169.254:80` for all users), but
  disabling `firewalld` during Phase 3.2 flushed the chain that had REJECTed the *rest* of
  `169.254.0.0/16`, so the surface is now slightly wider. Host-level `OUTPUT` rules are the wrong fix
  here — the right control is a Kubernetes NetworkPolicy denying pod egress to `169.254.0.0/16`,
  applied once the cluster is up. *Noted: 2026-09-24, during Phase 3.2.*

- [ ] **Finish the Postgres backup path — `BACKUP_PAR_URL` is not set yet.** `k8s/backup.yaml`
  deploys a nightly CronJob (03:00 UTC) that dumps Postgres and uploads it off-node, but it
  references a `BACKUP_PAR_URL` key that does not exist in the `feedme-secrets` Secret, so every run
  fails at container creation until it is added. Remaining steps: create an Object Storage bucket
  (`feedme-backups`) and a **Bucket**-type pre-authenticated request with **object writes only**
  (write-only on purpose — a compromised node then cannot read or delete existing backups), add the
  PAR URL to the Secret, trigger a manual run, and **test an actual restore** rather than assuming
  the dump is good. Also worth an ADR once it works, and note PARs expire: when it does, backups
  fail silently. *Noted: 2026-09-24, during Phase 3.7.*
