# ADR 0018: Shape of the Kubernetes manifests

Status: Accepted

## Context

Phase 3.5 translates `docker-compose.yml`'s five services into Kubernetes objects for the single-node
k3s cluster chosen in [ADR-0016](0016-oracle-cloud-k3s-over-aws.md). Most of it is mechanical - the
images don't change, and the three coupling env vars (`DATABASE_URL`, `REDIS_URL`,
`FEEDME_API_URL`) get the same treatment they already get in Compose, because Kubernetes Services
provide DNS by name exactly like Compose networks do. A handful of choices were not mechanical.

## Decision

**Postgres runs as a Deployment with `strategy: Recreate`, not a StatefulSet.** Convention says
StatefulSet for databases, and that convention earns its keep with multiple ordered replicas and
per-replica volumes. Neither exists here: one node, one replica, one PVC. `Recreate` is required
either way - the default `RollingUpdate` briefly runs old and new pods together, which two Postgres
processes cannot do on one `ReadWriteOnce` volume. Cost: a few seconds of downtime per db deploy.
Revisit if replication is ever added.

**Migrations move from the api container's `CMD` into an init container.** [ADR-0012](0012-dockerize-api-and-ui-as-separate-images.md)
put `alembic upgrade head && uvicorn ...` in the Dockerfile and noted the limit: it stops being safe
above one API replica. An init container keeps the same single-owner property that ADR-0012 wanted
while making it structural - Kubernetes guarantees it runs to completion before the app container
starts, and it runs once per pod rather than racing. The worker still runs no migrations at all.

**Every Service is `ClusterIP`; nothing binds a node port.** Compose publishes 5432 and 6379 to the
host, which is convenient locally and unacceptable on an internet-facing node. External traffic
arrives only through the Ingress in 3.7, which terminates TLS and routes to the `ui` and `api`
Services. Postgres and Redis are reachable only from inside the cluster.

**Secrets are referenced key-by-key, not with a blanket `envFrom`.** Each pod sees only what it
reads: `db` gets `POSTGRES_PASSWORD`; `worker` gets `DATABASE_URL` and `ANTHROPIC_API_KEY` (its
import chain never reaches `app.api.auth`, so it has no use for `JWT_SECRET_KEY` or
`FEEDME_REGISTRATION_CODE`, despite Compose handing it both via `env_file`); `api` gets those four
but not `POSTGRES_PASSWORD`; `redis` and `ui` get none at all. Keeping the UI credential-free is the
property [ADR-0004](0004-streamlit-for-phase-0-ui.md) and [ADR-0015](0015-jwt-multi-user-auth.md)
were after, now enforced at the cluster level rather than only by convention.

**`imagePullPolicy: IfNotPresent` everywhere.** Not cosmetic: the default for a `latest` tag is
`Always`, which makes k3s try to pull from Docker Hub and fail for images side-loaded onto the node
(3.4). Should become immutable per-commit tags in 3.8, at which point this can go.

**Kustomize (`kubectl apply -k k8s/`) over five loose `-f` flags.** Gives one place to set the
namespace, and gives 3.8's pipeline `kustomize edit set image` for tag rewriting instead of sed-ing
YAML. `labels` uses `includeSelectors: false` - baking an extra label into a Deployment's selector
makes it immutable and painful to change later.

**No probes on the worker.** It exposes no port, and the obvious liveness check (`celery inspect
ping`) is slow and prone to false negatives under load - it would restart healthy workers
mid-ingestion. The retry classification already in `app/worker.py` covers the failure mode that
matters.

## Consequences

- Gain: the stack is described declaratively and provider-agnostically, as ADR-0016 called for -
  nothing here is Oracle-specific, so a move to another cluster is a config change.
- Gain: secrets are least-privilege per pod, tighter than the Compose setup they replace.
- Cost: a few seconds of write downtime whenever the db Deployment rolls.
- Cost: `latest` tags mean `kubectl rollout` can't tell versions apart until 3.8 introduces real tags.
- Not yet validated against a live API server - `kubectl` needs a cluster to fetch schemas, so these
  have only been rendered and cross-checked offline. First real apply is 3.3/3.5-on-cluster.
- Revisit when: a second API replica is genuinely needed (init-container migrations hold, but the
  Recreate/RWO story for Postgres does not), or Postgres outgrows a single in-cluster pod.
