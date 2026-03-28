# Workflows

## Ingest Workflow
```mermaid
sequenceDiagram
    participant Producer as Cloudflare Logpush (example)
    participant API as edge-ingest-api
    participant Kafka as Kafka
    participant Worker as edge-ingest-worker
    participant ES as Elasticsearch

    Producer->>API: POST /
    API->>Kafka: produce edge-logpush batch
    Kafka-->>API: durable write ack
    API-->>Producer: 2xx response
    Worker->>Kafka: consume batch
    Worker->>ES: bulk index to edge-logs alias
    ES-->>Worker: success or item errors
    Worker->>Kafka: commit offset or route DLQ
```

### What to watch
- API success rate
- producer errors
- Kafka lag
- worker error rate
- Elasticsearch write queue and rejections
- freshness of indexed events

## Investigation Workflow
```mermaid
sequenceDiagram
    participant Grafana
    participant API as investigation-ops-api
    participant Kafka as Kafka
    participant Worker as investigation-ops-worker
    participant ES as Elasticsearch
    participant Notify as Notification route

    Grafana->>API: webhook alert payload
    API->>Kafka: produce investigations job
    Worker->>Kafka: consume job
    Worker->>ES: query edge-logs
    Worker->>Worker: run playbook logic
    Worker->>ES: write investigation-results-v1
    Worker->>Notify: send summary
```

### What to watch
- webhook acceptance rate
- job backlog on `investigations`
- Elasticsearch query latency for playbooks
- investigation result indexing success
- notification failures

## Deployment Sequencing
The sequencing rule is:
1. infra
2. platform
3. apps
4. runtime bootstrap
5. smoke validation

Do not invert that order. The services depend on runtime objects and secrets that do not exist after the infra layer alone.

## Operational Failure Modes
### Kafka lag grows while API stays healthy
This usually means the system is accepting traffic but search indexing throughput is behind current ingress. Check:
- consumer throughput
- Elasticsearch hot-tier write pressure
- current write index shard layout
- worker concurrency and batch settings

### Elasticsearch is green but data is late
This usually means the search cluster is healthy enough to write, but it is consuming backlog rather than fresh traffic. Check:
- Kafka lag
- event time versus ingest time in dashboards
- current write index freshness

### Investigation jobs are accepted but no results appear
Check:
- `investigations` topic depth
- worker logs
- playbook selection rules
- Elasticsearch permissions and target index lifecycle
