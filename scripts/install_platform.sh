#!/bin/zsh
set -euo pipefail
REPO="$(cd -- "$(dirname -- "$0")/.." && pwd)"

kubectl create namespace kafka --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace grafana --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace investigations --dry-run=client -o yaml | kubectl apply -f -

python3 "$REPO/scripts/render_secret_templates.py"
kubectl apply -f "$REPO/rendered/secrets/grafana-admin-secret.yaml"

kubectl apply -f https://download.elastic.co/downloads/eck/3.2.0/crds.yaml
kubectl apply -f https://download.elastic.co/downloads/eck/3.2.0/operator.yaml

helm repo add bitnami https://charts.bitnami.com/bitnami >/dev/null 2>&1 || true
helm repo add grafana https://grafana.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update >/dev/null

helm upgrade --install kafka bitnami/kafka \
  --namespace kafka \
  --version 32.4.3 \
  -f "$REPO/k8s/platform/kafka/values.yaml"

helm upgrade --install grafana grafana/grafana \
  --namespace grafana \
  --version 10.5.15 \
  -f "$REPO/k8s/platform/grafana/values.yaml"

kubectl apply -f "$REPO/k8s/platform/elasticsearch/search-stack.yaml"
kubectl apply -f "$REPO/k8s/platform/elasticsearch/kibana.yaml"
