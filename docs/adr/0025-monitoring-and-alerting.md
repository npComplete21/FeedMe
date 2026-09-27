# ADR 0025: Monitoring and alerting for the silent failure modes

Status: Accepted

## Context

By the end of Phase 3 the system had accumulated four failure modes that produced **no signal at
all** — every pod stays green, the site keeps serving, and you find out when a user complains or
months later:

- the backup pre-authenticated request expires and uploads stop ([ADR-0023](0023-postgres-backups-to-object-storage.md))
- YouTube cookies expire and gated videos start failing ([ADR-0024](0024-youtube-anti-bot-check.md))
- cert-manager renewal fails, and the site breaks 30 days later
- the Celery worker wedges — it has no liveness probe by design ([ADR-0018](0018-kubernetes-manifest-shape.md))

Surveying the running system for the design turned up two more that were worse than the ones already
known:

- **`local-path` puts the Postgres PVC on the node's root filesystem.** The `10Gi` request is a
  claim, not a reservation, so container images and the database compete for the same 30GB. A disk
  filled by image churn is *data loss*, not a failed pull. Disk had gone 49% → 69% in a single day
  of deploys.
- **Redis had no `maxmemory` and the default `noeviction` policy**, so growth ends in *refused
  writes* — ingestion failing silently — rather than eviction.

## Decision

**Fix what can be prevented; alert on the rest.** Alerting on a problem that a config change would
have eliminated is the worse trade. So Redis is capped at 200mb with `allkeys-lru` (below its 256Mi
container limit, so it sheds data before the kernel OOM-kills it), and kubelet image GC moved from
85/80 to 70/55 to stop images crowding out Postgres.

**Prometheus + Grafana + Alertmanager in-cluster**, via k3s's helm-controller. Heavier than a
scheduled external script — ~140Mi RAM and ~3GB disk on a 10GB/30GB node — and chosen anyway,
because this project is explicitly a vehicle for learning how systems are operated and this is the
industry-standard stack. Seven FeedMe-specific rules sit alongside the chart's ~220 generic ones.

**Alerts go to phone push via ntfy**, templated so a notification reads `FeedmeBackupStale / No
successful Postgres backup in over 26 hours` rather than raw Alertmanager JSON. The topic is a
credential — anyone holding it can read every alert — and this repository is public, so it lives in
a Kubernetes Secret referenced by `url_file`. `repeat_interval` is 24h, not the usual 4h:
re-notification is a reminder about something already known.

**An external watchdog closes the blind spot in-cluster monitoring cannot.** Prometheus cannot alert
that Prometheus is down; Alertmanager cannot report that its node is gone. A scheduled GitHub
Actions job therefore checks, every 30 minutes and from outside: the site returns 200, the
certificate has >10 days left, and **Prometheus is still firing its `Watchdog` alert**. Watchdog
fires continuously by design as proof the rule-evaluation and notification path work — so its
*absence* is the signal. It is routed to the null receiver in Alertmanager precisely because
pushing a constant heartbeat to a phone is noise; its value is realised only by something outside
noticing when it stops.

## Consequences

- Gain: all six failure modes now produce a push notification. **It proved itself immediately** —
  on first evaluation the rules caught that the previous night's scheduled backup had failed with
  `DeadlineExceeded`, a real incident nobody would otherwise have seen.
- Cost: ~140Mi RAM and ~3GB disk, on a node that was already at 60%. Non-trivial on hardware this
  small, and the reason image GC was tightened in the same change.
- **Known gap: GitHub disables scheduled workflows on repositories inactive for 60 days.** An
  abandoned project loses its external watchdog silently — the same class of failure this exists to
  prevent. Accepted rather than solved; a third-party dead man's switch would avoid it.
- Two bugs of mine, both recorded because the symptoms misdirected:
  - The operator rejected the config with `line 49: field storage not found in type config.plain`,
    which reads like an Alertmanager schema problem. It was a stranded YAML block from a string
    replacement that silently reparented `storage` under `config`. The values block is now parsed
    and asserted before being applied.
  - Grafana at a 256Mi limit was `OOMKilled` (exit 137) on startup. Raised to 512Mi from
    observation, not guesswork.
- Revisit when: a second node exists (Alertmanager clustering, and the blind spot narrows), or when
  alert volume justifies routing by severity rather than everything to one topic.
