from __future__ import annotations

import asyncio
from pathlib import Path

from elasticsearch import AsyncElasticsearch

from app.core.settings import Settings
from app.models.investigation import InvestigationResult


RESULT_INDEX_MAPPING = {
    "mappings": {
        "dynamic": True,
        "properties": {
            "schema_version": {"type": "keyword"},
            "incident_id": {"type": "keyword"},
            "job_id": {"type": "keyword"},
            "source_index_alias": {"type": "keyword"},
            "playbook_id": {"type": "keyword"},
            "preliminary_abuse_type_hypothesis": {"type": "keyword"},
            "confidence": {"type": "float"},
            "notification_status": {"type": "keyword"},
            "processing_status": {"type": "keyword"},
            "processed_at": {"type": "date"},
            "alert_metadata": {"type": "object", "dynamic": True},
            "time_window": {"type": "object", "dynamic": True},
            "extracted_features": {"type": "object", "dynamic": True},
            "top_suspicious_entities": {"type": "nested"},
            "recommended_next_queries": {"type": "nested"},
            "recommended_mitigations": {"type": "keyword"},
            "evidence_summary": {"type": "text"},
            "error": {"type": "text"},
        }
    }
}


class ElasticsearchInvestigationClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncElasticsearch | None = None
        self._result_index_ready = False

    async def start(self) -> None:
        if self._client:
            return

        client_options = {
            "hosts": [self._settings.elasticsearch_url],
            "request_timeout": self._settings.elasticsearch_request_timeout_seconds,
        }
        if self._settings.elasticsearch_username and self._settings.elasticsearch_password:
            client_options["basic_auth"] = (
                self._settings.elasticsearch_username,
                self._settings.elasticsearch_password,
            )

        ca_path = Path(self._settings.elasticsearch_ca_cert_path)
        if ca_path.exists():
            client_options["ca_certs"] = str(ca_path)

        self._client = AsyncElasticsearch(**client_options)

    async def stop(self) -> None:
        if not self._client:
            return
        await self._client.close()
        self._client = None
        self._result_index_ready = False

    async def ping(self) -> bool:
        if not self._client:
            return False
        return bool(await self._client.ping())

    async def execute_queries(self, index: str, alert_query: dict, baseline_query: dict) -> tuple[dict, dict]:
        if not self._client:
            raise RuntimeError("Elasticsearch client is not started")
        alert_result, baseline_result = await asyncio.gather(
            self._client.search(index=index, body=alert_query),
            self._client.search(index=index, body=baseline_query),
        )
        return alert_result, baseline_result

    async def ensure_result_index(self) -> None:
        if not self._client or self._result_index_ready:
            return
        exists = await self._client.indices.exists(index=self._settings.result_index)
        if not exists:
            await self._client.indices.create(
                index=self._settings.result_index,
                body=RESULT_INDEX_MAPPING,
            )
        self._result_index_ready = True

    async def persist_result(self, result: InvestigationResult) -> None:
        if not self._client:
            raise RuntimeError("Elasticsearch client is not started")
        await self.ensure_result_index()
        await self._client.index(
            index=self._settings.result_index,
            id=result.job_id,
            document=result.model_dump(mode="json"),
            refresh="wait_for",
        )

    @property
    def ready(self) -> bool:
        return self._client is not None
