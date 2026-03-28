from __future__ import annotations

import json

from aiokafka import AIOKafkaProducer

from app.core.settings import Settings
from app.models.investigation import InvestigationJob


class KafkaInvestigationProducer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        if self._producer:
            return
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            client_id=self._settings.kafka_client_id,
            request_timeout_ms=self._settings.kafka_request_timeout_ms,
            value_serializer=lambda value: json.dumps(value, default=str).encode("utf-8"),
        )
        await self._producer.start()

    async def stop(self) -> None:
        if not self._producer:
            return
        await self._producer.stop()
        self._producer = None

    async def publish_job(self, job: InvestigationJob) -> None:
        if not self._producer:
            raise RuntimeError("Kafka producer is not started")
        await self._producer.send_and_wait(
            self._settings.investigation_job_topic,
            job.model_dump(mode="json"),
            key=job.incident_id.encode("utf-8"),
        )

    @property
    def ready(self) -> bool:
        return self._producer is not None

