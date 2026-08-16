# ADR 0016: Oracle Cloud Always Free + k3s, not AWS

Status: Accepted — supersedes [ADR-0005](0005-k3s-vs-eks.md)

## Context

[ADR-0005](0005-k3s-vs-eks.md) framed Phase 3's decision as "k3s vs EKS," implicitly assuming AWS as
the deployment target. A cost analysis across the realistic options showed AWS's cheapest path
(k3s on a `t4g.small` EC2 instance) still runs ~$15-20/mo, and EKS runs ~$105-175/mo — dominated not
by actual compute needs (this app is tiny at ~50 users) but by fixed architecture fees: EKS's
$73/mo control-plane charge and, if following AWS's recommended private-subnet setup, a ~$32/mo NAT
Gateway. Oracle Cloud Infrastructure's "Always Free" tier offers up to 4 OCPUs / 24GB RAM of ARM
(Ampere A1) compute, 200GB storage, and 10TB/month egress — genuinely free forever, not a 12-month
trial like AWS's free tier — which is large enough to run this app's entire stack (Postgres, Redis,
API, worker, UI) with substantial headroom, at $0/mo.

## Decision

**Deploy on a single Oracle Cloud Ampere A1 VM, running k3s.** This keeps the actual Kubernetes
learning goal intact (real manifests, real `kubectl`, same k3s software AWS's k3s-on-EC2 path would
have used) while eliminating the AWS-specific fixed costs entirely. The only recurring cost is a
domain name (~$10-15/year); TLS is free either way via Let's Encrypt.

**Accepted tradeoffs, made explicit:**
- **Free-tier ARM capacity is sometimes hard to obtain at signup** — Oracle is known for
  "out of host capacity" errors on Always Free Ampere instances in popular regions, occasionally
  requiring retries. A cost of time, not money.
- **ARM (`arm64`) architecture** — Docker images must build for `arm64`, not `amd64`. The base images
  already in use (Python, Postgres, Redis, official Streamlit) all publish multi-arch variants, so
  this is a build-flag change, not a rewrite.
- **Self-managed, single node, no control-plane HA** — identical tradeoff to what the AWS
  k3s-on-EC2 path in ADR-0005 would already have accepted; nothing lost by moving providers.
- **Less "resume-relevant AWS experience"** than EKS would have given — explicitly not the goal
  here; the goal (per user) is learning how scalable systems are built generally, and cost took
  priority over which specific cloud brand appears on a resume.
- Kubernetes manifests are still written to stay provider-agnostic (same principle ADR-0005 already
  called for) — nothing here rules out moving to EKS or another cloud later if requirements change.

## Consequences

- Gain: $0/mo hosting cost vs ~$15-175/mo across the AWS options.
- Gain: k3s + kubectl + real manifests, so the Kubernetes learning goal survives the provider switch.
- Cost: capacity-at-signup friction, ARM builds, and no free managed Postgres equivalent to RDS —
  Postgres runs in-cluster on the same node, backed up manually rather than by a managed service.
- Revisit when: usage genuinely outgrows a single 4-OCPU/24GB node, or the free-tier capacity/account
  risk becomes a real operational problem rather than a signup inconvenience — at that point, the
  provider-agnostic manifests make moving to EKS (or Oracle's own paid tier) a config change, not a
  rewrite.
