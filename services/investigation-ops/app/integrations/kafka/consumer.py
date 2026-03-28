from __future__ import annotations

import json

from aiokafka import AIOKafkaConsumer
from aiokafka.structs import OffsetAndMetadata, TopicPartition

from app.core.settings import Settings


class KafkaInvestigationConsumer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        if self._consumer:
            return
        self._consumer = AIOKafkaConsumer(
            self._settings.investigation_job_topic,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            client_id=f"{self._settings.kafka_client_id}-worker",
            group_id=self._settings.investigation_consumer_group,
            enable_auto_commit=False,
            request_timeout_ms=self._settings.kafka_request_timeout_ms,
            auto_offset_reset="latest",
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
        await self._consumer.start()

    async def stop(self) -> None:
        if not self._consumer:
            return
        await self._consumer.stop()
        self._consumer = None

    async def getmany(self, *, timeout_ms: int, max_records: int) -> dict:
        if not self._consumer:
            raise RuntimeError("Kafka consumer is not started")
        return await self._consumer.getmany(timeout_ms=timeout_ms, max_records=max_records)

    async def commit_message(self, message) -> None:
        if not self._consumer:
            raise RuntimeError("Kafka consumer is not started")
        topic_partition = TopicPartition(message.topic, message.partition)
        await self._consumer.commit(
            {topic_partition: OffsetAndMetadata(message.offset + 1, "")}
        )

    @property
    def ready(self) -> bool:
        return self._consumer is not None

