# Architecture

## Design Goals
- decouple ingest acknowledgement from Elasticsearch indexing latency
- preserve logs during spikes and transient search outages
- keep search storage operationally manageable through hot and warm tiers
- make alerting and investigations first-class platform concerns
- keep runtime contracts declarative and reproducible

## Reference Producer Example
This repo uses Cloudflare Logpush as the concrete producer example because it is a common real-world HTTP log shipping pattern.

That choice is illustrative, not restrictive. The same design works for any producer that can send batched HTTP log payloads.

## Platform Topology
The platform has five active areas:
- `observability`: ingest API, ingest worker, Elasticsearch, Kibana, and the operator-managed search cluster
- `kafka`: durable buffering for ingest and investigation jobs
- `grafana`: dashboards, alerting, contact points, and notification policy
- `monitoring`: Prometheus and Elasticsearch exporter
- `investigations`: webhook intake and investigation workers

## Data Plane
### 1. HTTP ingest
- A producer such as Cloudflare Logpush sends batches to the `edge-ingest` service.
- The service routes to `edge-ingest-api` pods.
- The API validates the payload and produces to Kafka.
- Kafka is the durability boundary for the acknowledgement path.

### 2. Indexing
- `edge-ingest-worker` consumes Kafka batches.
- Workers bulk index into Elasticsearch through the `edge-logs` alias.
- ILM and index templates control shard count, rollover, retention, and tier movement.

### 3. Search and dashboards
- Grafana and Kibana query the search cluster.
- Grafana alert rules drive investigation webhook calls and operational notifications.

## Investigation Plane
- Grafana sends selected alerts to `investigation-ops-api`.
- The API normalizes requests into Kafka jobs on `investigations`.
- `investigation-ops-worker` processes jobs using YAML playbooks.
- Results are written to `investigation-results-v1` and can also feed notification routes.

## Why The Split Ingest Model Matters
Using separate API and worker roles solves two different problems:
- the API remains lightweight and latency-focused
- the worker can be tuned independently for search throughput and retry behavior

That separation is the central production decision in this repo. It matters more than the exact replica counts.

## Why Kafka Sits In The Middle
Kafka is not optional decoration. It is the safety margin between bursty producers and a search backend with finite write throughput.

Operationally this gives you:
- a durable ACK boundary
- replay and inspection when workers or Elasticsearch fall behind
- separate producer and consumer scaling
- a DLQ pattern that does not contaminate the main topic

## Why Hot/Warm Search Exists
Search storage is split because recent data and older data have different cost and performance needs.

- hot tier: active write path and recent query load
- warm tier: cheaper storage for older data that still needs investigation access

The practical lesson is that retention and write throughput must be sized together. Hot and warm capacity are not independent decisions.

## Runtime Objects Matter
A lot of production behavior is not encoded in plain deployment manifests. This repo keeps those runtime objects explicit:
- Kafka topic definitions and configs
- Elasticsearch ILM policies
- Elasticsearch index templates and aliases
- Elasticsearch ingest pipelines
- Grafana datasources, dashboards, alert rules, contact points, and policies

Without these objects, a rebuilt cluster can look healthy while behaving differently.

## Components And Contracts
| Component | Responsibility | Key contract |
| --- | --- | --- |
| `edge-ingest-api` | HTTP intake and Kafka production | `POST /`, `GET /healthz`, `edge-logpush` |
| `edge-ingest-worker` | Kafka consume and bulk indexing | `edge-logpush`, `edge-logpush-dlq`, `edge-logs` |
| Kafka | durable buffering | topic configs under `runtime/kafka/topics.json` |
| Elasticsearch | log storage and investigation queries | ILM/templates/aliases under `runtime/elasticsearch` |
| Grafana | dashboards and alert routing | assets under `runtime/grafana` |
| `investigation-ops-api` | webhook normalization | Grafana webhook payload to Kafka job |
| `investigation-ops-worker` | deterministic playbook execution | `investigations`, `investigation-results-v1` |

## Production Tradeoffs
- **Throughput vs storage overhead:** more primary shards can increase write concurrency but increase shard overhead.
- **Retention vs capacity:** long warm retention drives disk pressure faster than most teams expect.
- **Fast ACK vs end-to-end completion:** acknowledging after Kafka durability improves availability, but it moves freshness monitoring to Kafka lag and consumer health.
- **Exactness vs portability:** this repo preserves production-grade runtime contracts while still keeping environment identity configurable.
