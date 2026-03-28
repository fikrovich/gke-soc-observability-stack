from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status

from app.core.logging import configure_logging, get_logger
from app.core.settings import Settings, get_settings
from app.integrations.elastic.client import ElasticsearchInvestigationClient
from app.integrations.kafka.consumer import KafkaInvestigationConsumer
from app.integrations.slack.client import SlackWebhookClient
from app.models.investigation import InvestigationJob
from app.playbooks.loader import load_playbooks
from app.services.investigation import InvestigationProcessor

logger = get_logger(__name__)


async def _consumer_loop(app: FastAPI) -> None:
    consumer: KafkaInvestigationConsumer = app.state.consumer
    processor: InvestigationProcessor = app.state.processor

    while True:
        records = await consumer.getmany(timeout_ms=1000, max_records=25)
        for _partition, messages in records.items():
            for message in messages:
                try:
                    job = InvestigationJob.model_validate(message.value)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "invalid_investigation_job",
                        extra={"error": str(exc), "raw_message": message.value},
                    )
                    await consumer.commit_message(message)
                    continue

                try:
                    result = await processor.process_job(job)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "investigation_job_retryable_failure",
                        extra={
                            "incident_id": job.incident_id,
                            "job_id": job.job_id,
                            "alert_uid": job.alert.fingerprint,
                            "playbook_id": job.playbook_id,
                            "error": str(exc),
                        },
                    )
                    continue

                if result.processing_status.value in {"completed", "failed"}:
                    await consumer.commit_message(message)
                logger.info(
                    "investigation_job_processed",
                    extra={
                        "incident_id": result.incident_id,
                        "job_id": result.job_id,
                        "alert_uid": result.alert_metadata.fingerprint,
                        "playbook_id": result.playbook_id,
                        "processing_status": result.processing_status.value,
                    },
                )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    playbooks = load_playbooks(
        settings.playbook_dir,
        field_mapping_overrides_path=settings.field_mapping_overrides_path,
    )
    elastic = ElasticsearchInvestigationClient(settings)
    slack = SlackWebhookClient(settings)
    consumer = KafkaInvestigationConsumer(settings)

    await elastic.start()
    if not await elastic.ping():
        raise RuntimeError("Elasticsearch ping failed")
    await slack.start()
    await consumer.start()

    processor = InvestigationProcessor(
        settings=settings,
        playbooks=playbooks,
        elastic=elastic,
        slack=slack,
    )

    app.state.settings = settings
    app.state.playbooks = playbooks
    app.state.elastic = elastic
    app.state.slack = slack
    app.state.consumer = consumer
    app.state.processor = processor
    app.state.ready = True
    app.state.consumer_task = asyncio.create_task(_consumer_loop(app))
    logger.info(
        "worker_started",
        extra={
            "service_name": settings.service_name,
            "kafka_bootstrap_servers": settings.kafka_bootstrap_servers,
            "elasticsearch_url": settings.elasticsearch_url,
        },
    )
    try:
        yield
    finally:
        app.state.ready = False
        consumer_task: asyncio.Task = app.state.consumer_task
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        await consumer.stop()
        await slack.stop()
        await elastic.stop()


app = FastAPI(title="Investigation Worker", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(request: Request) -> dict[str, str]:
    if not getattr(request.app.state, "ready", False):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="not ready")
    elastic: ElasticsearchInvestigationClient = request.app.state.elastic
    consumer: KafkaInvestigationConsumer = request.app.state.consumer
    if not elastic.ready or not consumer.ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="dependencies not ready")
    return {"status": "ready"}


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.worker.main:app",
        host=settings.worker_host,
        port=settings.worker_port,
        log_config=None,
        reload=False,
    )


if __name__ == "__main__":
    main()
