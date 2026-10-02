# Runbook: move Postgres onto its own block volume

**Status: not yet run.** Closes the last part of the backlog's "node disk" item: Postgres's data
lives in a `local-path` PVC on the node's root disk, so anything that fills that disk (images,
Prometheus, logs) threatens the database ([ADR-0025](../adr/0025-monitoring-and-alerting.md)).
Giving Postgres its own OCI block volume separates the two.

Expect ~15 minutes of downtime (API, worker and UI can't reach the database while it's copied).

> **Don't commit the manifest change in step 6 before steps 1-5 are done.** `deploy.yml` applies
> `k8s/` on every `v*` tag; a PV pointing at `/mnt/pgdata` before that directory is a mounted,
> populated volume would start Postgres on an empty directory.

## 1. Create and attach the volume (OCI console)

1. Check Always Free headroom first: 200 GB of block storage in total, **including the boot
   volume**. Storage → Block Volumes and Compute → Boot Volumes show what's used.
2. Storage → Block Volumes → Create: same availability domain as the instance, 50 GB, default
   performance. Name it `feedme-pgdata`.
3. Compute → Instances → (the node) → Attached block volumes → Attach: the new volume,
   **Paravirtualized**, read/write. Paravirtualized needs no iSCSI commands on the node.

## 2. Format and mount it (on the node)

```
ssh opc@132.145.213.150
lsblk                                   # the new, empty 50G disk, e.g. /dev/sdb - CHECK the name
sudo mkfs.ext4 -L pgdata /dev/sdb       # only on the new, empty disk
sudo mkdir -p /mnt/pgdata
echo 'LABEL=pgdata /mnt/pgdata ext4 defaults,noatime,_netdev,nofail 0 2' | sudo tee -a /etc/fstab
sudo mount -a && df -h /mnt/pgdata
```

`nofail` keeps a missing volume from blocking boot; Postgres then fails to start rather than the
node failing to come up - recoverable over SSH.

## 3. Take a fresh backup

```
kubectl create job -n feedme --from=cronjob/db-backup db-backup-before-move
kubectl wait -n feedme --for=condition=complete job/db-backup-before-move --timeout=10m
```

## 4. Stop everything that writes, then the database

```
kubectl scale -n feedme deploy/api deploy/worker --replicas=0
kubectl scale -n feedme deploy/db --replicas=0
kubectl wait -n feedme --for=delete pod -l app=db --timeout=2m
```

## 5. Copy the data directory

```
PV=$(kubectl get pvc -n feedme db-data -o jsonpath='{.spec.volumeName}')
SRC=$(kubectl get pv "$PV" -o jsonpath='{.spec.hostPath.path}{.spec.local.path}')
echo "$SRC"                              # /var/lib/rancher/k3s/storage/pvc-..._feedme_db-data
sudo rsync -aHAX --numeric-ids "$SRC"/ /mnt/pgdata/
sudo chown -R 999:999 /mnt/pgdata
sudo du -sh "$SRC" /mnt/pgdata           # sizes should match
```

## 6. Point the manifests at the new volume

In `k8s/db.yaml`, add a static PV + a new claim and switch the Deployment's `claimName` to it:

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: db-data-block
spec:
  capacity: {storage: 50Gi}
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain   # deleting the claim must never wipe the data
  storageClassName: ""                    # static - keep local-path from provisioning one
  local:
    path: /mnt/pgdata
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - {key: kubernetes.io/hostname, operator: Exists}
  claimRef: {namespace: feedme, name: db-data-block}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: db-data-block
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: ""
  volumeName: db-data-block
  resources: {requests: {storage: 50Gi}}
```

…and in the Deployment: `claimName: db-data-block`. Leave the old `db-data` PVC in the file for
now. Then:

```
kubectl apply -k k8s/                    # never -f on a single file (ADR-0020)
kubectl get pvc -n feedme db-data-block  # Bound
```

`PersistentVolume` is cluster-scoped; the kustomization's `namespace: feedme` doesn't affect it.

## 7. Start up and verify

```
kubectl scale -n feedme deploy/db --replicas=1
kubectl rollout status -n feedme deploy/db
kubectl exec -n feedme deploy/db -- psql -U feedme -c 'select count(*) from recipes' -c 'select count(*) from users'
kubectl exec -n feedme deploy/db -- df -h /var/lib/postgresql/data   # shows the 50G volume
kubectl scale -n feedme deploy/api deploy/worker --replicas=1
```

Then log in at https://feedmepls.xyz and open a recipe.

**Rollback** (any step fails before the old PVC is deleted): set `claimName: db-data` back,
`kubectl apply -k k8s/`, scale up. The old directory is untouched by the copy.

## 8. Afterwards

- Commit the `k8s/db.yaml` change, with the PV/PVC above.
- Add an alert for the new mount: copy `FeedmeNodeDiskFilling` in `k8s/monitoring-rules.yaml`
  with `mountpoint="/mnt/pgdata"`.
- After a week of normal running and a successful nightly backup, remove the old `db-data` PVC
  from `k8s/db.yaml` and delete it (`kubectl delete pvc -n feedme db-data`), which frees its root
  disk space.
- Tick off the backlog item and record the decision in an ADR.
