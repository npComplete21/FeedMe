# ADR 0022: Build on merge, deploy on tag, over SSH

Status: Accepted

## Context

Phase 3.8 had to replace a manual deploy - rebuild locally, `docker save | ssh` into containerd,
`kubectl rollout restart` - with a pipeline. Three things had to be decided.

## Decision

**Native `arm64` runners, not QEMU.** The cluster is Ampere A1, so images must be `linux/arm64`.
`ubuntu-24.04-arm` runners are free for public repos and build natively; emulating arm64 on an amd64
runner would rebuild `psycopg` and `pydantic` wheels under QEMU on every run. Measured result: three
images build in parallel in roughly 45 seconds each.

**Build on every merge to `main`, deploy only on a `v*` tag.** `ci.yml` runs the test suite and
publishes images tagged with the commit SHA; `deploy.yml` deploys the image already built for the
tagged commit rather than rebuilding it. This keeps "built" and "released" as separate decisions -
merging is safe, releasing is deliberate - and guarantees the artifact that was tested is the
artifact that ships.

**The runner reaches the cluster over SSH, not the Kubernetes API.** Port 6443 stays closed to the
internet as [ADR-0019](0019-single-firewall-layer-on-the-node.md) intended. CI renders the manifests
locally with `kustomize build` and pipes them to `kubectl apply -f -` on the node over SSH. The
alternative - opening 6443 to GitHub's published IP ranges - would undo a deliberate decision in
exchange for convenience, and those ranges are broad and change.

A **dedicated passphraseless deploy key** is used, not the personal one. The personal key is
passphrase-protected (correct for a human, unusable in CI), and a CI credential should be revocable
without disturbing human access.

**Image substitution lives in `kustomization.yaml`'s `images` block**, so CI rewrites one place.
This retires the `:latest` tags [ADR-0018](0018-kubernetes-manifest-shape.md) flagged as temporary:
deploys now pin an immutable per-commit tag, which is what makes `kubectl rollout undo` and
`rollout status` meaningful rather than decorative.

**Three guards, each for a failure the pipeline would otherwise have:**
- `build` depends on `test`, so a failing suite cannot publish an image.
- `deploy` verifies all three images exist for the tagged commit *before* touching the cluster.
  Without it, tagging a commit that never reached `main` would half-apply and leave pods in
  `ImagePullBackOff`.
- `deploy` ends by requiring `https://feedmepls.xyz` to return 200, so a green run means the site
  serves - not merely that pods restarted.

## Consequences

- Gain: releasing is `git tag -a v0.2.0 && git push origin v0.2.0`, and rollback is
  `kubectl rollout undo` against a real previous image rather than an unchanged `:latest`.
- Gain: GHCR packages inherit the repo's public visibility, so the node pulls anonymously and there
  is no registry credential in the cluster. Verified: a cold pull took 3.9s.
- Cost: the node must now reach `ghcr.io`, where before images were side-loaded. Acceptable - it
  already needs outbound internet for the Claude API.
- Cost: a deploy key with cluster-admin-equivalent reach exists as a GitHub secret. It is
  passphraseless by necessity; the mitigation is that it is dedicated and independently revocable.
- Three bugs were found by running it rather than by review, all now fixed: buildx's default
  `docker` driver cannot export a GHA cache (needs `setup-buildx-action`); the runner already ships
  `kustomize` and its installer refuses to overwrite; and `curl --retry-all-errors` combined with
  `-w` exited 23 without reporting a status, so the smoke test is now an explicit loop that prints
  each attempt.
- Revisit when: there is more than one environment (the tag currently means exactly one production),
  or when deploys need approval gates rather than being automatic on tag.
