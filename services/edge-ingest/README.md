# Edge Ingest Service

FastAPI-based ingest service for batched HTTP log pushes, using Cloudflare Logpush as the reference producer example.

The active design is split:
- `edge-ingest-api` receives HTTP payloads and durably enqueues them to Kafka
- `edge-ingest-worker` consumes Kafka batches and bulk indexes them into Elasticsearch

The same image supports both roles. Behavior is selected through environment variables and deployment shape.

## Why This Service Exists
This service solves a production problem that a direct HTTP-to-Elasticsearch path does not solve well:
- producers need a fast acknowledgement path
- Elasticsearch write throughput is finite
- backlog and retries need to be isolated from producer availability

So the service acknowledges after Kafka durability, not after full search indexing.

## Runtime Modes
### Kafka-backed mode
Default and recommended.

- HTTP endpoint produces to `edge-logpush`
- background consumer writes to `edge-logs`
- failures can be routed to `edge-logpush-dlq`

### Direct-to-search mode
Supported as a legacy fallback through `INGEST_MODE=es`.

This is not the primary deployment model in this repo.

## HTTP Contract
- `POST /`: accepts the producer batch
- `GET /health`: returns API, Kafka, and Elasticsearch health summary
- `GET /metrics`: returns lightweight runtime counters
- `GET /`: returns service metadata and route hints

## Key Environment Variables
### Shared
- `AUTH_TOKEN`
- `MAX_REQUEST_SIZE_BYTES`
- `LOG_LEVEL`

### Kafka path
- `INGEST_MODE=kafka`
- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_TOPIC=edge-logpush`
- `KAFKA_DLQ_TOPIC=edge-logpush-dlq`
- `KAFKA_GROUP_ID=edge-logpush-workers`
- `KAFKA_PRODUCER_MAX_REQUEST_SIZE`
- `KAFKA_CONSUMER_MAX_PARTITION_FETCH_BYTES`
- `KAFKA_MAX_POLL_INTERVAL_MS`

### Elasticsearch path
- `ES_HOST`
- `ES_USER`
- `ES_PASSWORD`
- `ES_INDEX=edge-logs`
- `ES_PIPELINE=EdgeEvents`
- `ES_TIMEOUT`
- `ES_MAX_RETRIES`
- `BATCH_SIZE`
- `MAX_CONCURRENT_BATCHES`

## Local Run
Create a virtual environment and install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the service in Kafka-backed mode:
```bash
export INGEST_MODE=kafka
export AUTH_TOKEN=replace-me
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export ES_HOST=http://localhost:9200
export ES_PASSWORD=replace-me
python app.py
```

Run the direct-to-search fallback mode:
```bash
export INGEST_MODE=es
export AUTH_TOKEN=replace-me
export ES_HOST=http://localhost:9200
export ES_PASSWORD=replace-me
python app.py
```

## Docker
Build:
```bash
docker build -t edge-ingest:local .
```

Run:
```bash
docker run --rm -p 8080:8080 \
  -e INGEST_MODE=kafka \
  -e AUTH_TOKEN=replace-me \
  -e KAFKA_BOOTSTRAP_SERVERS=host.docker.internal:9092 \
  -e ES_HOST=http://host.docker.internal:9200 \
  -e ES_PASSWORD=replace-me \
  edge-ingest:local
```

## Kubernetes Deployment Model
The supported manifests live under `k8s/namespaces/observability/`.

The active split deployment is:
- `edge-ingest-api`
- `edge-ingest-worker`
- `edge-ingest` service targeting the API pods

## Cloudflare Example
This repo uses Cloudflare Logpush as the concrete producer example because it is a common real-world source of batched HTTP edge logs.

What matters in that integration:
- the endpoint returns success only after Kafka durability
- request size limits match the producer behavior
- dashboards measure both queue lag and indexed freshness

## Operational Signals
Watch these first:
- API success rate
- Kafka lag on `edge-logpush`
- worker errors and DLQ volume
- Elasticsearch write queue and rejections
- freshness of the newest indexed event
