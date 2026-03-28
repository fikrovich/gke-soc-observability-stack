#!/bin/zsh
set -euo pipefail
REPO="$(cd -- "$(dirname -- "$0")/.." && pwd)"
RENDERED_K8S="$REPO/rendered/k8s"

wait_rollout() {
  local namespace="$1"
  local kind_name="$2"
  local timeout="${3:-600s}"
  kubectl rollout status "$kind_name" -n "$namespace" --timeout="$timeout"
}

wait_jsonpath() {
  local namespace="$1"
  local resource="$2"
  local jsonpath="$3"
  local regex="$4"
  local timeout_seconds="${5:-1200}"
  local deadline=$((SECONDS + timeout_seconds))

  while (( SECONDS < deadline )); do
    value="$(kubectl get -n "$namespace" "$resource" -o "jsonpath=${jsonpath}" 2>/dev/null || true)"
    if [[ "$value" =~ $regex ]]; then
      return 0
    fi
    sleep 10
  done

  echo "Timed out waiting for $resource in $namespace to match $regex (last value: $value)" >&2
  return 1
}

kubectl create namespace kafka --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace grafana --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace investigations --dry-run=client -o yaml | kubectl apply -f -

python3 "$REPO/scripts/render_secret_templates.py" --scope grafana
kubectl apply -f "$REPO/rendered/secrets/grafana-admin-secret.yaml"

kubectl apply -f https://download.elastic.co/downloads/eck/3.2.0/crds.yaml
kubectl apply -f https://download.elastic.co/downloads/eck/3.2.0/operator.yaml
wait_rollout elastic-system statefulset/elastic-operator 600s

helm repo add bitnami https://charts.bitnami.com/bitnami >/dev/null 2>&1 || true
helm repo add grafana https://grafana.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update >/dev/null

helm upgrade --install kafka bitnami/kafka \
  --namespace kafka \
  --version 32.4.3 \
  -f "$RENDERED_K8S/platform/kafka/values.yaml"
wait_rollout kafka statefulset/kafka-controller 900s
wait_rollout kafka statefulset/kafka-broker 900s

helm upgrade --install grafana grafana/grafana \
  --namespace grafana \
  --version 10.5.15 \
  -f "$RENDERED_K8S/platform/grafana/values.yaml"
wait_rollout grafana deployment/grafana 600s

kubectl apply -f "$RENDERED_K8S/platform/elasticsearch/search-stack.yaml"
kubectl apply -f "$RENDERED_K8S/platform/elasticsearch/kibana.yaml"
wait_jsonpath observability "elasticsearch/${SEARCH_CLUSTER_NAME:-search-stack}" '{.status.health}' 'green|yellow' 1800
wait_jsonpath observability "kibana/${SEARCH_UI_NAME:-kibana}" '{.status.health}' 'green|yellow' 1200
