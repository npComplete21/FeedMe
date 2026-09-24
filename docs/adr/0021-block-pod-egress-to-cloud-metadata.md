# ADR 0021: Block pod egress to the OCI metadata service with a NetworkPolicy

Status: Accepted

## Context

`169.254.169.254` returns instance identity and, where configured, credentials. Any process on the
node could reach it, including any container - the standard SSRF-to-cloud-metadata escalation, and
exactly the thing a compromised pod benefits from. This was not theoretical: a test pod received
`HTTP 200` from the metadata endpoint before this policy existed.

The exposure predates us - Oracle's shipped `OUTPUT` rules already `ACCEPT`ed `169.254.169.254:80`
for all users - but disabling `firewalld` in 3.2 ([ADR-0019](0019-single-firewall-layer-on-the-node.md))
flushed the chain that had rejected the *rest* of `169.254.0.0/16`, widening it slightly.

## Decision

**A namespace-wide `NetworkPolicy` on egress, not host-level `OUTPUT` rules.** Host rules cannot
distinguish pod traffic from the node's own, and the node legitimately needs metadata access for
iSCSI and cloud-init. A NetworkPolicy applies to pods specifically, which is the actual boundary.

**Expressed as "allow everything except", because NetworkPolicy has no deny rule.** It is an
allow-list model, so blocking one range means writing a single egress rule permitting `0.0.0.0/0`
with `except: [169.254.0.0/16]`. That one rule therefore has to carry all legitimate egress too -
CoreDNS, pod-to-pod, the Claude API, Object Storage for backups - all of which fall inside
`0.0.0.0/0` and are unaffected. kube-router encodes this correctly as an ipset containing
`0.0.0.0/1` and `128.0.0.0/1` with `169.254.0.0/16 nomatch`.

Verified rather than assumed, in both directions: from a settled pod, metadata fails to connect
(curl exit 7) while `api.anthropic.com` and the in-cluster `api` Service both succeed, and a full
recipe ingestion - which requires worker egress to the Claude API - still completes.

## Consequences

- Gain: a compromised pod can no longer read instance metadata, and this is enforced by the cluster
  rather than by host firewall state that a `systemctl` command can flush.
- **Caveat worth knowing: enforcement is not instantaneous.** kube-router programs a per-pod chain
  after the pod starts, so a very short-lived pod can egress unrestricted before its rules exist.
  This was observed directly - a `kubectl run --rm` pod reached metadata successfully, while the
  same image in a pod left alive for 30 seconds was blocked. The policy is a strong control against
  a compromised long-running workload, not a hard guarantee against a deliberately ephemeral one.
- Cost: the rule is inverted and reads oddly - "allow the internet except one /16" rather than
  "deny one /16". That is a NetworkPolicy limitation, not a choice, and is commented in the manifest
  so nobody later "simplifies" it into something that allows nothing.
- Scoped to the `feedme` namespace. `kube-system` and `cert-manager` pods are unaffected and can
  still reach metadata; extending it would need checking that nothing there depends on it.
- Revisit when: a second namespace runs workloads, or if egress ever needs to be genuinely
  default-deny rather than default-allow-minus-one-range.
