# ADR 0005: k3s vs EKS for the Phase 3 deployment target

Status: Proposed — not yet decided, revisit when Phase 3 starts

## Context

The goal is to deploy on Kubernetes on AWS. Two realistic options:

- **EKS**: AWS's managed control plane. Control plane alone costs ~$73/mo before any compute or
  RDS. In exchange: a fully managed, standard, resume-relevant setup that integrates cleanly
  with IAM, the AWS Load Balancer Controller, EBS/EFS CSI drivers, etc.
- **k3s on a single EC2 instance**: a lightweight k8s distribution running on one small node
  (e.g. `t4g.small`, ~$10-15/mo). Real Kubernetes manifests, real `kubectl`, but self-managed —
  no control-plane HA, and you're responsible for upgrades/patching the node yourself.

For a personal, single-to-small-multi-user app, EKS's managed HA control plane is solving a
problem (control-plane availability at scale) this project doesn't have yet. The deciding
factor is really *why* we want k8s at all: if the goal is production-grade AWS experience
specifically (e.g. for resume/job purposes), EKS is the more honest choice. If the goal is
learning Kubernetes concepts and mechanics cheaply, k3s gets there for a fraction of the cost.

## Decision

Not yet made — deferred until Phase 3. Leaning toward k3s on a single EC2 instance for cost
reasons, unless the specific goal of gaining hands-on EKS experience outweighs that.

## Consequences

Whichever is chosen, the Kubernetes manifests/Helm charts written for the app should stay
provider-agnostic where possible (avoid EKS-specific add-ons unless deliberately adopted), so
switching between them later isn't a full rewrite.
