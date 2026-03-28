#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi

SEARCH_NAMESPACE="${SEARCH_NAMESPACE:-observability}"
SEARCH_CLUSTER_NAME="${SEARCH_CLUSTER_NAME:-search-stack}"
INVESTIGATION_NAMESPACE="${INVESTIGATION_NAMESPACE:-investigations}"

kubectl get secret -n "$SEARCH_NAMESPACE" "${SEARCH_CLUSTER_NAME}-es-http-certs-public" -o jsonpath='{.data.tls\.crt}' | base64 --decode > /tmp/investigation-search-ca.crt
kubectl create secret generic investigation-search-ca \
  -n "$INVESTIGATION_NAMESPACE" \
  --from-file=tls.crt=/tmp/investigation-search-ca.crt \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/investigation-search-ca.crt
