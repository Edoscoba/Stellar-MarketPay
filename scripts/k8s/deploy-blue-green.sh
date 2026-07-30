#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <primary|secondary> <immutable-image-tag> [kubectl-context]" >&2
  exit 2
}

[[ $# -ge 2 && $# -le 3 ]] || usage

cluster_role=$1
image_tag=$2
context=${3:-}
namespace=stellar-marketpay
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
overlay="$repo_root/k8s/overlays/$cluster_role"

[[ "$cluster_role" == "primary" || "$cluster_role" == "secondary" ]] || usage
[[ "$image_tag" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] || {
  echo "Image tag must be immutable and contain only registry-safe characters." >&2
  exit 2
}
[[ "$image_tag" != "latest" && "$image_tag" != "replace-with-immutable-tag" ]] || {
  echo "Refusing a mutable or placeholder image tag." >&2
  exit 2
}
command -v kubectl >/dev/null || {
  echo "kubectl is required." >&2
  exit 2
}
kubectl argo rollouts version --client >/dev/null || {
  echo "The kubectl Argo Rollouts plugin is required." >&2
  exit 2
}

kubectl_args=()
if [[ -n "$context" ]]; then
  kubectl_args+=(--context "$context")
fi

for crd in \
  rollouts.argoproj.io \
  analysistemplates.argoproj.io \
  externalsecrets.external-secrets.io \
  gslbs.k8gb.io; do
  kubectl "${kubectl_args[@]}" get crd "$crd" >/dev/null || {
    echo "Required CRD is missing: $crd" >&2
    exit 1
  }
done

rendered=$(
  kubectl kustomize "$overlay" |
    sed "s/:replace-with-immutable-tag/:$image_tag/g"
)
if grep -q "replace-with-immutable-tag" <<<"$rendered"; then
  echo "Image placeholder remained after rendering." >&2
  exit 1
fi

printf '%s\n' "$rendered" | kubectl "${kubectl_args[@]}" apply -f -

kubectl "${kubectl_args[@]}" -n "$namespace" wait \
  --for=condition=Ready externalsecret/marketpay-backend-secrets \
  externalsecret/marketpay-frontend-secrets --timeout=3m

failed=0
for rollout in marketpay-backend marketpay-frontend; do
  if ! kubectl argo rollouts status "$rollout" \
    "${kubectl_args[@]}" -n "$namespace" --timeout=15m; then
    failed=1
  fi
done

if ((failed)); then
  echo "A rollout failed. Argo Rollouts will restore the stable ReplicaSet when post-promotion analysis fails." >&2
  kubectl "${kubectl_args[@]}" -n "$namespace" get \
    rollout,analysisrun,pods -o wide >&2 || true
  exit 1
fi

# These objects were created by the pre-blue-green manifests. Argo has already
# made its stable ReplicaSets active, so removing them cannot interrupt traffic.
for legacy in \
  deployment/marketpay-backend \
  deployment/marketpay-frontend \
  horizontalpodautoscaler/marketpay-backend-hpa \
  horizontalpodautoscaler/marketpay-frontend-hpa; do
  if kubectl "${kubectl_args[@]}" -n "$namespace" get "$legacy" >/dev/null 2>&1; then
    kubectl "${kubectl_args[@]}" -n "$namespace" delete "$legacy"
  fi
done

kubectl "${kubectl_args[@]}" -n "$namespace" get rollout,gslb
echo "Blue-green deployment completed in $cluster_role with tag $image_tag."
