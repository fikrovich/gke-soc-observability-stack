#!/usr/bin/env python3
"""
Edge Logpush ingestion service.

Mode "kafka" (default):
- HTTP endpoint durably enqueues payload to Kafka (send_and_wait)
- returns 2xx only after Kafka ACK
- background worker consumes from Kafka and writes to Elasticsearch
- failed consume/write payloads are sent to DLQ topic

Mode "es":
- legacy direct write path to Elasticsearch from HTTP request
"""

import asyncio
import gzip
import json
import logging
import os
import random
from datetime import datetime
from typing import Optional

import httpx
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import CommitFailedError, KafkaError, MessageSizeTooLargeError
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

# Core configuration
INGEST_MODE = os.getenv("INGEST_MODE", "kafka").lower()  # kafka|es
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "your-secret-token-here")
MAX_REQUEST_SIZE = int(os.getenv("MAX_REQUEST_SIZE_BYTES", str(50 * 1024 * 1024)))

# Elasticsearch configuration
ES_HOST = os.getenv("ES_HOST", "https://search-stack-es-http.observability:9200")
ES_USER = os.getenv("ES_USER", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD")
ES_INDEX = os.getenv("ES_INDEX", "edge-logs")
ES_PIPELINE = os.getenv("ES_PIPELINE", "EdgeEvents")
ES_TIMEOUT = int(os.getenv("ES_TIMEOUT", "8"))
MAX_RETRIES = int(os.getenv("ES_MAX_RETRIES", "1"))
BACKOFF_BASE = float(os.getenv("BACKOFF_BASE", "1.0"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))
MAX_CONCURRENT_BATCHES = int(os.getenv("MAX_CONCURRENT_BATCHES", "3"))

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.kafka.svc.cluster.local:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "edge-logpush")
KAFKA_DLQ_TOPIC = os.getenv("KAFKA_DLQ_TOPIC", "edge-logpush-dlq")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "edge-logpush-workers")
KAFKA_PRODUCER_MAX_REQUEST_SIZE = int(os.getenv("KAFKA_PRODUCER_MAX_REQUEST_SIZE", str(50 * 1024 * 1024)))
KAFKA_CONSUMER_MAX_PARTITION_FETCH_BYTES = int(
    os.getenv("KAFKA_CONSUMER_MAX_PARTITION_FETCH_BYTES", str(50 * 1024 * 1024))
)
KAFKA_MAX_POLL_INTERVAL_MS = int(os.getenv("KAFKA_MAX_POLL_INTERVAL_MS", "900000"))
PROCESSOR_ENABLED = os.getenv("PROCESSOR_ENABLED", "true").lower() == "true"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title="Edge Ingest", version="3.0.0-kafka")

# Global clients/tasks
es_client: Optional[httpx.AsyncClient] = None
kafka_producer: Optional[AIOKafkaProducer] = None
kafka_consumer: Optional[AIOKafkaConsumer] = None
consumer_task: Optional[asyncio.Task] = None

METRICS = {
    "start_time": None,
    "http_requests": 0,
    "http_bytes_received": 0,
    "kafka_enqueued": 0,
    "kafka_enqueue_failures": 0,
    "kafka_consumed": 0,
    "kafka_dlq_sent": 0,
    "kafka_dlq_failures": 0,
    "es_processed": 0,
    "es_sent": 0,
    "es_errors": 0,
    "es_retries": 0,
    "es_429_count": 0,
    "es_503_count": 0,
    "dropped_docs": 0,
}


def _header_value(headers: list[tuple[str, bytes]], key: str) -> str:
    wanted = key.lower()
    for h_key, h_val in headers:
        if h_key.lower() == wanted:
            try:
                return h_val.decode("utf-8")
            except Exception:
                return ""
    return ""


def transform_log_to_bulk(log: dict) -> tuple[dict, dict]:
    ray_id = log.get("RayID")
    create_meta = {"_index": ES_INDEX}
    if ray_id:
        create_meta["_id"] = ray_id
    return {"create": create_meta}, log


async def send_batch_to_es(batch: list[tuple[dict, dict]], attempt: int = 0) -> dict:
    if not batch:
        return {"items": [], "errors": False}

    bulk_lines = []
    for index_meta, doc in batch:
        bulk_lines.append(json.dumps(index_meta, separators=(",", ":")))
        bulk_lines.append(json.dumps(doc, separators=(",", ":")))
    bulk_data = "\n".join(bulk_lines) + "\n"

    try:
        response = await es_client.post(
            f"{ES_HOST}/_bulk?pipeline={ES_PIPELINE}&refresh=false",
            content=bulk_data,
            headers={"Content-Type": "application/x-ndjson", "Accept-Encoding": "gzip"},
            auth=(ES_USER, ES_PASSWORD),
        )

        if response.status_code in (429, 503):
            if response.status_code == 429:
                METRICS["es_429_count"] += 1
            else:
                METRICS["es_503_count"] += 1

            if attempt < MAX_RETRIES:
                wait_time = (BACKOFF_BASE * (2**attempt)) + random.uniform(0, 0.5)
                METRICS["es_retries"] += 1
                await asyncio.sleep(wait_time)
                return await send_batch_to_es(batch, attempt + 1)

            METRICS["dropped_docs"] += len(batch)
            METRICS["es_errors"] += len(batch)
            return {"items": [], "errors": True, "dropped": len(batch)}

        response.raise_for_status()
        result = response.json()

        if result.get("errors"):
            error_items = [i for i in result.get("items", []) if i.get("create", {}).get("error")]
            if error_items:
                METRICS["es_errors"] += len(error_items)
        return result

    except httpx.TimeoutException:
        if attempt < MAX_RETRIES:
            METRICS["es_retries"] += 1
            await asyncio.sleep(BACKOFF_BASE * (2**attempt))
            return await send_batch_to_es(batch, attempt + 1)
        METRICS["dropped_docs"] += len(batch)
        METRICS["es_errors"] += len(batch)
        raise


async def process_payload_to_es(payload: bytes, content_encoding: str = "") -> dict:
    data = payload
    if content_encoding and "gzip" in content_encoding.lower():
        data = gzip.decompress(payload)

    lines = data.split(b"\n")
    batch = []
    pending_tasks: list[tuple[asyncio.Task, int]] = []
    total_processed = 0
    total_sent = 0
    total_errors = 0

    for line in lines:
        if not line.strip():
            continue
        try:
            log = json.loads(line)
            total_processed += 1
            batch.append(transform_log_to_bulk(log))

            if len(batch) >= BATCH_SIZE:
                task = asyncio.create_task(send_batch_to_es(batch.copy()))
                pending_tasks.append((task, len(batch)))
                batch = []

                if len(pending_tasks) >= MAX_CONCURRENT_BATCHES:
                    oldest, count = pending_tasks.pop(0)
                    result = await oldest
                    total_sent += count
                    if result.get("errors"):
                        total_errors += count
        except Exception:
            total_errors += 1

    if batch:
        pending_tasks.append((asyncio.create_task(send_batch_to_es(batch)), len(batch)))

    for task, count in pending_tasks:
        try:
            result = await task
            total_sent += count
            if result.get("errors"):
                total_errors += count
        except Exception:
            total_errors += count

    METRICS["es_processed"] += total_processed
    METRICS["es_sent"] += total_sent
    METRICS["es_errors"] += total_errors

    return {"processed": total_processed, "sent": total_sent, "errors": total_errors}


async def publish_to_dlq(value: bytes, headers: list[tuple[str, bytes]], reason: str) -> None:
    dlq_headers = list(headers)
    dlq_headers.append(("dlq-reason", reason[:240].encode("utf-8", errors="ignore")))
    try:
        await kafka_producer.send_and_wait(KAFKA_DLQ_TOPIC, value=value, headers=dlq_headers)
        METRICS["kafka_dlq_sent"] += 1
    except Exception as exc:
        METRICS["kafka_dlq_failures"] += 1
        logger.error(f"DLQ publish failed: {exc}")


async def consume_loop() -> None:
    logger.info(f"Kafka consumer started: topic={KAFKA_TOPIC}, group={KAFKA_GROUP_ID}")
    try:
        async for msg in kafka_consumer:
            METRICS["kafka_consumed"] += 1
            content_encoding = _header_value(msg.headers or [], "content-encoding")
            header_list = [(k, v) for k, v in (msg.headers or [])]
            try:
                await process_payload_to_es(msg.value, content_encoding)
            except Exception as exc:
                logger.error(f"Worker processing failed, sending to DLQ: {exc}")
                await publish_to_dlq(msg.value, header_list, str(exc))
            finally:
                # Rebalances can invalidate the current generation between processing and commit.
                # Do not crash the consumer loop on commit race; continue and rejoin.
                try:
                    await kafka_consumer.commit()
                except CommitFailedError as exc:
                    logger.warning(f"Kafka commit skipped after rebalance: {exc}")
    except asyncio.CancelledError:
        logger.info("Kafka consumer loop cancelled")
        raise
    except Exception as exc:
        logger.exception(f"Kafka consumer loop crashed: {exc}")


@app.on_event("startup")
async def startup_event() -> None:
    global es_client, kafka_producer, kafka_consumer, consumer_task

    METRICS["start_time"] = datetime.now().isoformat()

    es_client = httpx.AsyncClient(
        verify=False,
        timeout=httpx.Timeout(float(ES_TIMEOUT), connect=5.0),
        limits=httpx.Limits(max_keepalive_connections=50, max_connections=100),
    )

    if INGEST_MODE == "kafka":
        kafka_producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            acks="all",
            enable_idempotence=True,
            compression_type="gzip",
            linger_ms=5,
            max_request_size=KAFKA_PRODUCER_MAX_REQUEST_SIZE,
            request_timeout_ms=20000,
        )
        await kafka_producer.start()

        if PROCESSOR_ENABLED:
            kafka_consumer = AIOKafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=KAFKA_GROUP_ID,
                enable_auto_commit=False,
                auto_offset_reset="latest",
                max_partition_fetch_bytes=KAFKA_CONSUMER_MAX_PARTITION_FETCH_BYTES,
                fetch_max_bytes=KAFKA_CONSUMER_MAX_PARTITION_FETCH_BYTES,
                max_poll_interval_ms=KAFKA_MAX_POLL_INTERVAL_MS,
            )
            await kafka_consumer.start()
            consumer_task = asyncio.create_task(consume_loop())

    logger.info(
        "Service started: mode=%s, kafka=%s, processor=%s, batch=%s, timeout=%ss",
        INGEST_MODE,
        KAFKA_BOOTSTRAP_SERVERS,
        PROCESSOR_ENABLED,
        BATCH_SIZE,
        ES_TIMEOUT,
    )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
    if kafka_consumer:
        await kafka_consumer.stop()
    if kafka_producer:
        await kafka_producer.stop()
    if es_client:
        await es_client.aclose()


@app.post("/")
async def ingest_logs(
    request: Request,
    authorization: str = Header(None),
    content_encoding: str = Header("", alias="Content-Encoding"),
):
    if authorization != f"Bearer {AUTH_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type and "text/plain" not in content_type:
        raise HTTPException(status_code=400, detail="Content-Type must be application/json or text/plain")

    payload = await request.body()
    if len(payload) > MAX_REQUEST_SIZE:
        raise HTTPException(status_code=413, detail=f"Payload too large (>{MAX_REQUEST_SIZE} bytes)")

    METRICS["http_requests"] += 1
    METRICS["http_bytes_received"] += len(payload)

    if INGEST_MODE == "kafka":
        headers = [
            ("content-encoding", (content_encoding or "").encode("utf-8")),
            ("content-type", content_type.encode("utf-8")),
            ("received-at", datetime.utcnow().isoformat().encode("utf-8")),
        ]
        try:
            await kafka_producer.send_and_wait(KAFKA_TOPIC, value=payload, headers=headers)
            METRICS["kafka_enqueued"] += 1
            return JSONResponse(
                status_code=202,
                content={
                    "status": "accepted",
                    "mode": "kafka",
                    "topic": KAFKA_TOPIC,
                    "bytes": len(payload),
                },
            )
        except MessageSizeTooLargeError:
            METRICS["kafka_enqueue_failures"] += 1
            raise HTTPException(status_code=413, detail="Payload exceeds Kafka max message size")
        except KafkaError as exc:
            METRICS["kafka_enqueue_failures"] += 1
            logger.error(f"Kafka enqueue failed: {exc}")
            raise HTTPException(status_code=503, detail="Queue unavailable")

    try:
        start_time = datetime.now()
        stats = await process_payload_to_es(payload, content_encoding)
        duration = (datetime.now() - start_time).total_seconds()
        return {
            "status": "success",
            "mode": "es",
            "statistics": stats,
            "duration_seconds": duration,
        }
    except Exception as exc:
        logger.exception(f"Direct ES ingestion failed: {exc}")
        raise HTTPException(status_code=500, detail="Direct ES ingestion failed")


@app.get("/health")
async def health_check():
    health = {"status": "healthy", "mode": INGEST_MODE}

    if INGEST_MODE == "kafka":
        health["kafka"] = {
            "producer": kafka_producer is not None,
            "processor_enabled": PROCESSOR_ENABLED,
            "consumer_running": bool(consumer_task and not consumer_task.done()),
            "topic": KAFKA_TOPIC,
            "dlq_topic": KAFKA_DLQ_TOPIC,
        }

    try:
        response = await es_client.get(f"{ES_HOST}/_cluster/health", auth=(ES_USER, ES_PASSWORD))
        es_health = response.json()
        health["elasticsearch"] = {
            "status": es_health.get("status", "unknown"),
            "unassigned_shards": es_health.get("unassigned_shards", 0),
        }
    except Exception as exc:
        health["elasticsearch"] = {"status": "unreachable", "error": str(exc)}
        if PROCESSOR_ENABLED:
            health["status"] = "degraded"

    status_code = 200 if health["status"] == "healthy" else 503
    return JSONResponse(status_code=status_code, content=health)


@app.get("/metrics")
async def get_metrics():
    uptime = 0
    if METRICS["start_time"]:
        uptime = (datetime.now() - datetime.fromisoformat(METRICS["start_time"])).total_seconds()

    return {
        **METRICS,
        "uptime_seconds": uptime,
        "config": {
            "mode": INGEST_MODE,
            "batch_size": BATCH_SIZE,
            "es_timeout": ES_TIMEOUT,
            "max_retries": MAX_RETRIES,
            "kafka_topic": KAFKA_TOPIC,
            "kafka_dlq_topic": KAFKA_DLQ_TOPIC,
            "processor_enabled": PROCESSOR_ENABLED,
        },
    }


@app.get("/")
async def root():
    return {
        "service": "Edge Ingest",
        "version": "3.0.0-kafka",
        "mode": INGEST_MODE,
        "endpoints": {
            "POST /": "ingest endpoint",
            "GET /health": "health",
            "GET /metrics": "metrics",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8080)
