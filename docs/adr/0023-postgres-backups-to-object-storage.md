# ADR 0023: Nightly Postgres backups to Oracle Object Storage

Status: Accepted

## Context

Until now there were no backups at all. [ADR-0016](0016-oracle-cloud-k3s-over-aws.md) noted Postgres
would be "backed up manually rather than by a managed service," but that never became a real
mechanism. Meanwhile the data sits in a `local-path` PVC - a directory on one node's disk - with
`reclaimPolicy: Delete`, on a free-tier instance, about to be handed to ~50 people. Node
termination, disk loss, or an accidental `kubectl delete pvc` would have destroyed everything, and
an instance was already terminated once during Phase 3.

## Decision

**A `pg_dump`, not a volume snapshot.** The `local-path` provisioner has no CSI snapshot support, so
snapshots weren't available - but a logical dump is the better artifact anyway: portable to any
Postgres, inspectable, and about 2KB for this dataset.

**Stored off-node in Oracle Object Storage** (20GB on Always Free, so $0). A backup on the same disk
as the database protects against nothing that would realistically destroy it.

**Authenticated with a write-only pre-authenticated request, not OCI API credentials.** One secret
URL, no key management in the cluster. Crucially it permits *writes only*: the cluster can upload
but cannot read or list. A compromised node therefore cannot exfiltrate user data or enumerate what
exists. The cost is that restores can't use it - they need a console download or a short-lived read
PAR - which is the right shape for an operation that should be rare and deliberate.

**Two containers, two official images.** `postgres:16` has `pg_dump` but ships no `curl` or `wget`;
`curlimages/curl` has no `pg_dump`. Rather than build and maintain a custom image for this, an init
container dumps to an `emptyDir` and the main container uploads from it.

**A size guard before upload.** A dump under 200 bytes is refused, because an empty gzip is ~20
bytes and storing a silently-truncated backup is worse than failing loudly.

**`activeDeadlineSeconds: 1800`.** Learned the hard way: while `BACKUP_PAR_URL` was missing, the pod
sat in `CreateContainerConfigError`, which kubelet retries forever. The job never terminated, and
`concurrencyPolicy: Forbid` then blocked every subsequent run - so one misconfiguration became 37
hours of no backups being *attempted*, with the schedule wedged rather than visibly erroring.

## Consequences

- Gain: a nightly dump off the node at 03:00 UTC, at no cost.
- **Verified, not assumed.** A dump was restored into a throwaway database on 2026-09-27: 2 recipes,
  1 user and 11 `recipe_ingredients` round-tripped intact, with the live database untouched. The
  upload path was separately confirmed by a manual run that logged a matching byte count.
- Gap worth naming: the *uploaded object itself* has not been downloaded and restored, because the
  write-only PAR makes that impossible without a read PAR. The dump format is proven restorable and
  the PUT returned success; object integrity in the bucket is taken on trust.
- **PARs expire, and backups then fail silently.** There is no alerting. The failure mode is uploads
  simply stopping while every pod stays green. Rotation steps are recorded outside the repo, with
  the URL itself, since the URL is a credential.
- Cost: `pg_dump` runs against the live database. At this size it is instant; at a size where it
  isn't, this would want a replica or a snapshot-based approach.
- Revisit when: the dataset grows enough that a nightly full dump is wasteful (point-in-time
  recovery via WAL archiving would be the next step), or when silent failure becomes unacceptable
  and the job needs to report success somewhere.
