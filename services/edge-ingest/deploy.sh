#!/bin/bash
set -e

# Edge Ingestion Service Deployment Script

PROJECT_ID="example-observability"
REGION="example-region-1"
IMAGE_NAME="edge-ingest"
IMAGE_TAG="latest"
FULL_IMAGE="gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "==> Building Docker image with Cloud Build..."
gcloud builds submit --config=cloudbuild.yaml --region=${REGION} .

echo "==> Getting Elasticsearch password..."
ES_PASSWORD=$(kubectl get secret -n observability search-stack-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)

echo "==> Generating auth token..."
AUTH_TOKEN=$(openssl rand -hex 32)
echo "Auth token: ${AUTH_TOKEN}"
echo "Save this token for Edge Logpush configuration!"

echo "==> Creating secret with ES password..."
kubectl create secret generic edge-ingest-secret \
  --from-literal=es-password="${ES_PASSWORD}" \
  --from-literal=auth-token="${AUTH_TOKEN}" \
  --namespace=observability \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> Deploying to Kubernetes..."
kubectl apply -f deployment.yaml

echo "==> Waiting for rollout..."
kubectl rollout status deployment/edge-ingest -n observability --timeout=120s

echo "==> Deployment complete!"
echo ""
echo "Service URL (internal): http://edge-ingest.observability"
echo "Full internal URL: http://edge-ingest.observability.svc.cluster.local"
echo ""
echo "Configure Edge Tunnel to route to:"
echo "  Service: http://edge-ingest.observability:80"
echo ""
echo "Configure Edge Logpush:"
echo "  destination_conf: \"https://YOUR-TUNNEL-HOSTNAME?header_Authorization=Bearer ${AUTH_TOKEN}\""
echo "  kind: \"edge\""
echo ""
echo "Check logs with:"
echo "  kubectl logs -f -n observability -l app=edge-ingest"
