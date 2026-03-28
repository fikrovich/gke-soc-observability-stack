from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, Response, status

from app.core.logging import configure_logging, get_logger
from app.core.retry import retry_async
from app.core.settings import Settings, get_settings
from app.integrations.kafka.producer import KafkaInvestigationProducer
from app.models.grafana import GrafanaWebhookPayload
from app.playbooks.loader import PlaybookRegistry, load_playbooks
from app.services.identifiers import payload_hash
from app.services.normalization import normalize_payload
from app.services.validation import validate_grafana_payload, validate_webhook_token

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    playbooks = load_playbooks(
        settings.playbook_dir,
        field_mapping_overrides_path=settings.field_mapping_overrides_path,
    )
    producer = KafkaInvestigationProducer(settings)
    await producer.start()
    app.state.settings = settings
    app.state.playbooks = playbooks
    app.state.producer = producer
    app.state.ready = True
    logger.info(
        "api_started",
        extra={
            "service_name": settings.service_name,
            "kafka_bootstrap_servers": settings.kafka_bootstrap_servers,
            "playbook_count": len(playbooks.playbooks),
        },
    )
    try:
        yield
    finally:
        app.state.ready = False
        await producer.stop()


app = FastAPI(title="Investigation API", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(request: Request) -> dict[str, str]:
    if not getattr(request.app.state, "ready", False):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="not ready")
    producer: KafkaInvestigationProducer = request.app.state.producer
    if not producer.ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="producer not ready")
    return {"status": "ready"}


@app.post("/webhooks/grafana", status_code=status.HTTP_202_ACCEPTED)
async def grafana_webhook(
    request: Request,
    response: Response,
    x_investigation_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    settings: Settings = request.app.state.settings
    playbooks: PlaybookRegistry = request.app.state.playbooks
    producer: KafkaInvestigationProducer = request.app.state.producer

    if not settings.webhook_shared_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WEBHOOK_SHARED_TOKEN is not configured",
        )
    if not validate_webhook_token(
        x_investigation_token,
        settings.webhook_shared_token,
        authorization,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="content type must be application/json",
        )

    raw_body = await request.body()
    if not raw_body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty payload")

    try:
        payload = GrafanaWebhookPayload.model_validate_json(raw_body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid Grafana payload: {exc}",
        ) from exc

    try:
        validate_grafana_payload(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    jobs, accepted = normalize_payload(
        payload,
        raw_payload_hash=payload_hash(raw_body),
        settings=settings,
        playbooks=playbooks,
        received_at=datetime.now(UTC),
    )
    for job in jobs:
        await retry_async(
            lambda job=job: producer.publish_job(job),
            attempts=settings.retry_attempts,
            backoff_seconds=settings.retry_backoff_seconds,
        )
        logger.info(
            "investigation_job_published",
            extra={
                "incident_id": job.incident_id,
                "job_id": job.job_id,
                "alert_uid": job.alert.fingerprint,
                "playbook_id": job.playbook_id,
            },
        )

    primary = accepted[0]
    response.headers["X-Investigation-Incident-Id"] = primary.incident_id
    response.headers["X-Investigation-Job-Id"] = primary.job_id
    return {
        "incident_id": primary.incident_id,
        "job_id": primary.job_id,
        "accepted_jobs": [item.model_dump(mode="json") for item in accepted],
        "alert_count": len(accepted),
    }


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,
        reload=False,
    )


if __name__ == "__main__":
    main()
