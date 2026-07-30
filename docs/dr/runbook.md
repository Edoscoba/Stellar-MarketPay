# Disaster-recovery and deployment runbook

## Ownership and access

The incident commander owns the decision log. The database operator owns writer
promotion. The platform operator owns Kubernetes and K8GB. Two-person approval
is required for manual database promotion or failback.

Operators need read/write access to both Kubernetes contexts, the managed
PostgreSQL control plane, authoritative DNS/K8GB, the replicated secret vault,
and the container registry.

## Automated regional failover

The normal sequence requires no Kubernetes mutation:

1. Primary Pods stop reporting Ready after backend dependency checks fail.
2. The managed PostgreSQL service detects regional loss and promotes the
   secondary regional endpoint.
3. Secondary backend readiness changes from 503/read-only to 200/writable.
4. K8GB removes unhealthy primary targets and publishes secondary targets.
5. Alerts verify public traffic is served by `secondary-cluster`.

During the event, record:

```bash
date -u
kubectl --context secondary -n stellar-marketpay get pods,rollout,gslb -o wide
curl -fsS https://secondary.marketpay.example.com/health/ready | jq
dig +short marketpay.example.com
curl -fsS https://marketpay.example.com/health/ready | jq
```

Escalate immediately if the secondary is not writable after five minutes or
public traffic has not recovered after ten minutes.

## Manual intervention

### Database did not promote

1. Freeze deployments and disable automated failback.
2. Confirm the original writer is unreachable from both regions.
3. Read the provider's replication-lag/WAL position. If lag exceeds 60 seconds,
   declare the RPO breach before proceeding.
4. With database-operator and incident-commander approval, promote the
   secondary using the provider control plane.
5. Confirm `/health/ready` reports `database.role=primary` and
   `database.writable=true`.
6. Confirm K8GB publishes only the secondary target. If it does not, inspect
   `kubectl describe gslb marketpay -n stellar-marketpay`; change DNS manually
   only after database authority is proven.

### Secret replication failed

Do not copy live Kubernetes Secrets between clusters. Verify the regional vault
replica, the `marketpay-global-secrets` ClusterSecretStore, and then force a
refresh:

```bash
kubectl --context secondary -n stellar-marketpay describe externalsecret
kubectl --context secondary -n stellar-marketpay annotate externalsecret \
  marketpay-backend-secrets force-sync="$(date +%s)" --overwrite
```

### Suspected split brain

Remove both regions from DNS, revoke application database credentials, and
identify the authoritative timeline/WAL position. Preserve logs. Do not merge
two writable histories. Rebuild the losing database from the chosen writer,
rotate credentials, validate escrow records against Stellar, and only then
restore one region.

## Blue-green deployment

The GitHub `Deploy Kubernetes Blue-Green` workflow accepts an immutable image
tag. It deploys secondary first, then primary. Argo's preview smoke analysis
gates cutover and post-promotion analysis automatically restores stable traffic
if health fails.

To inspect a failure:

```bash
kubectl -n stellar-marketpay get rollout,analysisrun,pods
kubectl -n stellar-marketpay describe rollout marketpay-backend
kubectl -n stellar-marketpay logs job/<analysis-job-name>
```

Do not deploy the primary if the secondary rollout failed. Do not use `latest`.

### One-time migration from the legacy manifests

The previous manifests created plaintext placeholder Secrets and an in-cluster
single-node PostgreSQL StatefulSet. Before the first multi-cluster deployment:

1. Back up and restore that database into the managed global PostgreSQL writer,
   then compare row counts and application smoke tests.
2. Prove PITR restore and cross-region replay.
3. Configure both regional vault replicas and their ClusterSecretStores.
4. Delete the legacy `marketpay-backend-secrets`,
   `marketpay-frontend-secrets`, and `marketpay-postgres-secrets` only after the
   vault values are verified. External Secrets will recreate the application
   Secrets.
5. Run the blue-green deployment. After both Rollouts are Healthy, the script
   removes only the superseded stateless Deployments and HPAs.
6. Retain the old PostgreSQL PVC read-only for the approved rollback-retention
   period. Its StatefulSet, Service, and PVC require a separate, approved
   decommission change; this script never deletes database storage.

## Failback

Failback is never automatic:

1. Repair the old primary region.
2. Rebuild its database replica from the current writer; never reuse its old
   data volume.
3. Wait until replay lag is below 30 seconds for at least 30 minutes.
4. Deploy the same immutable application digest and run smoke checks.
5. Perform a managed database switchover during an approved window.
6. Verify the new writer, then restore the `primary-cluster` preference in
   K8GB.
7. Monitor errors, escrow operations, replication, and DNS for one hour.

## Game day

Run quarterly and after any database, DNS, ingress, secret-store, or rollout
controller change:

```bash
python3 scripts/dr/gameday.py \
  --mode live \
  --primary-url https://primary.marketpay.example.com/health/ready \
  --secondary-url https://secondary.marketpay.example.com/health/ready \
  --public-url https://marketpay.example.com/health/ready \
  --secondary-region secondary-cluster \
  --failure-command './approved-provider-region-isolation-command' \
  --restore-command './approved-provider-region-restore-command' \
  --report-json artifacts/dr-gameday.json \
  --report-markdown artifacts/dr-gameday.md
```

The harness refuses planned injection when the replica is unhealthy or replay
lag exceeds the RPO. Attach both reports, provider events, K8GB events, DNS
observations, and application metrics to the incident record.

Never run destructive failure injection without an approved maintenance window,
named incident commander, recent backup restore proof, and confirmed secondary
capacity.
