# ADR 0019: One firewall layer on the k3s node, not two

Status: Accepted

## Context

The Oracle Linux 9 image ships with `firewalld` active, allowing only `ssh` and `dhcpv6-client`.
Separately, the OCI security list attached to the VCN gates inbound traffic before it ever reaches
the host. Phase 3.2 had to decide whether to keep both layers or rely on one.

k3s and `firewalld` have a documented bad interaction on RHEL-family distributions. k3s programs its
own nftables/iptables rules for pod and service networking, and `firewalld` managing the same tables
is a recognised cause of intermittent CNI failures - DNS resolving sporadically, pods unable to reach
each other - which are disproportionately unpleasant to diagnose. k3s's own documentation recommends
disabling `firewalld` on Oracle Linux/RHEL/CentOS, or at minimum adding the pod (`10.42.0.0/16`) and
service (`10.43.0.0/16`) CIDRs to a trusted zone.

## Decision

**Disable `firewalld` and let the OCI security list be the single inbound boundary.**

This is not the same as running without a firewall. The security list is a real stateful firewall
enforced in the VCN, outside the host - architecturally the same model as AWS security groups, where
nobody considers an EC2 instance unprotected for lacking host-level iptables. It currently permits
22, 80 and 443 from `0.0.0.0/0` and nothing else. Port 6443 was verified filtered from outside, so
the Kubernetes API server is not internet-facing; `kubectl` reaches it over an SSH tunnel.

On a single-node cluster the host layer buys little that the security list does not already provide,
while costing a whole class of hard-to-debug networking bugs. One firewall that reliably works beats
two that may fight.

## Consequences

- Gain: no `firewalld`/k3s CNI interference, and one place to reason about inbound access.
- Cost: no defence in depth at the host. If the security list is ever misconfigured, nothing behind
  it will catch the mistake. Mitigated by keeping the rule set tiny and auditable - three ports.
- **Unintended, discovered during the change:** stopping `firewalld` also flushed Oracle's
  `BareMetalInstanceServices` iptables chain, which governed access to the `169.254.0.0/16`
  link-local range. There is no `iptables-save` file and no unit that restores it, so it is gone on
  this instance. Nothing broke - the `OUTPUT` policy is `ACCEPT`, so iSCSI boot-volume traffic still
  flows - and the practical delta is small, because that chain already `ACCEPT`ed the metadata
  endpoint (`169.254.169.254:80`) for all users; only the *other* link-local addresses were
  rejected. The residual exposure that does matter in a Kubernetes context - a compromised pod
  querying instance metadata - is tracked in the backlog, and its correct fix is a NetworkPolicy
  denying pod egress to `169.254.0.0/16`, not host `OUTPUT` rules.
- Revisit when: the node stops being single-purpose (anything else running on it would want host
  isolation), or the cluster gains nodes, at which point inter-node traffic needs deliberate rules
  rather than an implicit `ACCEPT`.
