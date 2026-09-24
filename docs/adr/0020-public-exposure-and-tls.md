# ADR 0020: How the cluster is exposed publicly, and how TLS is obtained

Status: Accepted

## Context

Phase 3.7 had to put the app on the internet at `feedmepls.xyz` with a trusted certificate. k3s ships
Traefik as its ingress controller (kept, see [ADR-0018](0018-kubernetes-manifest-shape.md)), and
cert-manager handles ACME. The decisions below are the ones that were not obvious.

## Decision

**The Ingress exposes the UI only; the API has no public route.** Streamlit renders server-side, so a
browser never talks to the API directly - it talks to the `ui` pod, which calls the API over the
cluster-internal Service (`FEEDME_API_URL=http://api:8000`). The API therefore needs no public route
for the application to work, and omitting one removes that attack surface for free. This preserves at
the network layer the same separation [ADR-0004](0004-streamlit-for-phase-0-ui.md) established at the
dependency layer. Adding `/api` later is one extra rule, worth doing only if direct API access is
actually wanted.

**Two ACME ClusterIssuers, and staging is used first.** Let's Encrypt rate-limits *failed*
validations at 5 per hostname per hour, and a freshly registered domain mid-propagation is exactly
when validation fails repeatedly. The Ingress pointed at `letsencrypt-staging` until a certificate
issued with both SANs, then switched to `letsencrypt-prod`. This was not theoretical: DNS took about
40 minutes to become resolvable inside the cluster, during which cert-manager retried continuously.
Against production those retries would likely have exhausted the limit.

**HTTP is redirected to HTTPS with a Traefik `Middleware`, including the ACME challenge path.** This
is safe - Let's Encrypt follows redirects during HTTP-01 validation and does not verify the
certificate on the redirected hop. **Port 80 must stay open at the OCI security list permanently**,
including after everything is HTTPS, because every renewal starts over plain HTTP.

## Consequences

- Gain: a real, auto-renewing certificate covering `feedmepls.xyz` and `www.feedmepls.xyz`, with no
  manual renewal step. cert-manager renews at 2/3 of the 90-day lifetime.
- Gain: the API and database are unreachable from the internet by construction, not by configuration
  that could drift.
- Cost: port 80 stays open forever, which is a requirement of HTTP-01 rather than a choice. A DNS-01
  solver would avoid it but needs registrar API credentials in the cluster - more secret material for
  less benefit here.
- **Operational trap discovered the hard way:** `kubectl apply -f k8s/ingress.yaml` bypasses the
  kustomization that injects `namespace: feedme`, so it silently created a *second* Ingress in
  `default` claiming the same hostnames and pointing at a nonexistent Service. It also obtained its
  own production certificate before being removed, consuming one of Let's Encrypt's 5-per-week
  duplicate-certificate allowances. **Always apply this directory with `kubectl apply -k k8s/`,
  never with `-f` on an individual file.**
- Revisit when: the API needs to be callable from outside the cluster (add a path rule), or a
  wildcard certificate is wanted (requires switching to a DNS-01 solver).
