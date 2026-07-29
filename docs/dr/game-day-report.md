# Disaster-recovery game-day report

## Control-plane simulation — 2026-07-29

Scope: deterministic execution of the failover coordinator with a healthy
read-only replica, loss of the primary endpoint, delayed DNS recovery, database
promotion, and restoration cleanup.

| Measurement | Target | Observed | Result |
| --- | ---: | ---: | --- |
| RTO | 600 seconds | 20 simulated seconds | Pass |
| RPO upper bound (replica replay lag at injection) | 60 seconds | 12 simulated seconds | Pass |

The simulation also verified that:

- failure injection is refused when replay lag is 31 seconds against a
  deliberately tightened 30-second test target;
- traffic is not considered recovered until the secondary database is writable;
- restoration runs after the exercise.

Gap found: the previous `/health` endpoint only ran `SELECT 1`, so a read-only
replica could be advertised as healthy. The new readiness response exposes
database role, writability, and replay lag; Kubernetes and K8GB now gate traffic
on it.

**Qualification:** this is control-plane automation evidence, not a production
region-loss certification. A live two-cluster game day requires organization
cluster, DNS, and managed-database credentials that are intentionally not stored
in this repository. The live command and evidence requirements are defined in
the runbook; its generated report must replace/supplement this report before the
10-minute/60-second production objectives are treated as proven.
