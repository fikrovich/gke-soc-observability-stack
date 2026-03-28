from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.settings import Settings
from app.models.grafana import GrafanaWebhookPayload
from app.playbooks.loader import load_playbooks
from app.services.investigation import InvestigationProcessor
from app.services.normalization import normalize_payload

ROOT = Path(__file__).resolve().parents[2]


class FakeElasticClient:
    def __init__(self) -> None:
        self.persisted = []

    async def execute_queries(self, index: str, alert_query: dict, baseline_query: dict) -> tuple[dict, dict]:
        return (
            {
                "hits": {"total": {"value": 900}},
                "aggregations": {
                    "top_ips": {"buckets": [{"key": "203.0.113.10", "doc_count": 450}]},
                    "top_asns": {"buckets": [{"key": 64512, "doc_count": 600}]},
                    "top_user_agents": {"buckets": [{"key": "Mozilla/5.0", "doc_count": 500}]},
                    "response_status": {"buckets": [{"key": 403, "doc_count": 400}]},
                    "security_actions": {"buckets": [{"key": "challenge", "doc_count": 320}]},
                    "security_rules": {"buckets": [{"key": "Checkout burst", "doc_count": 250}]},
                    "top_paths": {"buckets": [{"key": "/critical-path", "doc_count": 700}]},
                    "top_devices": {"buckets": [{"key": "device-123", "doc_count": 500}]},
                    "top_client_hints": {"buckets": [{"key": "client-abc", "doc_count": 550}]},
                    "top_sessions": {"buckets": [{"key": "session-xyz", "doc_count": 500}]}
                }
            },
            {
                "aggregations": {
                    "requests_over_time": {
                        "buckets": [{"doc_count": 100}] * 6
                    }
                }
            },
        )

    async def persist_result(self, result) -> None:
        self.persisted.append(result)


class FakeSlackClient:
    configured = True

    def __init__(self) -> None:
        self.payloads = []

    async def send(self, payload: dict) -> None:
        self.payloads.append(payload)


def build_settings() -> Settings:
    return Settings.model_validate(
        {
            "PLAYBOOK_DIR": str(ROOT / "config/playbooks"),
            "KAFKA_BOOTSTRAP_SERVERS": "kafka.kafka.svc.cluster.local:9092",
            "ELASTICSEARCH_INDEX_ALIAS": "edge-logs",
        }
    )


@pytest.mark.asyncio
async def test_processor_persists_and_sends_slack() -> None:
    raw_payload = (ROOT / "tests/fixtures/grafana_webhook_payload.json").read_bytes()
    payload = GrafanaWebhookPayload.model_validate(json.loads(raw_payload))
    playbooks = load_playbooks(ROOT / "config/playbooks")
    settings = build_settings()
    jobs, _ = normalize_payload(
        payload,
        raw_payload_hash="payload-hash",
        settings=settings,
        playbooks=playbooks,
        received_at=datetime(2026, 3, 14, 10, 5, tzinfo=UTC),
    )

    elastic = FakeElasticClient()
    slack = FakeSlackClient()
    processor = InvestigationProcessor(
        settings=settings,
        playbooks=playbooks,
        elastic=elastic,
        slack=slack,
    )

    result = await processor.process_job(jobs[0])

    assert result.processing_status.value == "completed"
    assert result.notification_status.value == "sent"
    assert len(elastic.persisted) == 2
    assert len(slack.payloads) == 1

