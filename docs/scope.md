# Scope

Included namespaces and components:
- `observability`
  - `edge-ingest-api`
  - `edge-ingest-worker`
  - `edge-ingest` LoadBalancer service
  - `search-stack` Elasticsearch cluster
  - `kibana`
  - `elastic-operator`
- `kafka`
  - Bitnami Kafka Helm release `kafka-32.4.3`
- `grafana`
  - Grafana Helm release `grafana-10.5.15`
- `monitoring`
  - `prometheus`
  - `elasticsearch-exporter`
- `investigations`
  - `investigation-ops-api`
  - `investigation-ops-worker`

Explicit exclusions:
- `semgrep`
- Cloud Run services
- GKE-managed namespaces
- inactive leftovers:
  - `observability/edge-ingest` deployment
  - `observability/logstash`
  - `observability/fleet-agents-http`
