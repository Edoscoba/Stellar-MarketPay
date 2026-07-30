# Multi-cluster Kubernetes deployment

The production topology is active-passive. Render and deploy the same base into
two independent clusters:

```bash
kubectl kustomize k8s/overlays/primary
kubectl kustomize k8s/overlays/secondary
scripts/k8s/deploy-blue-green.sh secondary "$IMAGE_TAG" secondary-context
scripts/k8s/deploy-blue-green.sh primary "$IMAGE_TAG" primary-context
```

Do not apply `k8s/base` directly. Before deployment, both clusters require:

- Argo Rollouts and its `Rollout`/`AnalysisTemplate` CRDs;
- the `kubectl-argo-rollouts` plugin on deployment runners;
- External Secrets Operator and a `ClusterSecretStore` named
  `marketpay-global-secrets`;
- K8GB configured with unique geo tags (`primary-cluster` and
  `secondary-cluster`) and delegated authoritative DNS;
- NGINX Ingress and cert-manager;
- regional managed-PostgreSQL endpoints supplied through the external secret.

The placeholder image tag is intentionally undeployable. The deployment script
requires an immutable tag, updates the passive cluster first, and waits for
Argo's pre- and post-promotion analysis before proceeding.

See [the DR architecture](../docs/dr/architecture.md) and
[operator runbook](../docs/dr/runbook.md).
