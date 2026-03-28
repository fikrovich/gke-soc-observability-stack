from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.settings import Settings
from app.models.grafana import GrafanaWebhookPayload
from app.playbooks.loader import load_playbooks
from app.services.normalization import normalize_payload

ROOT = Path(__file__).resolve().parents[2]


def build_settings() -> Settings:
    return Settings.model_validate(
        {
            "PLAYBOOK_DIR": str(ROOT / "config/playbooks"),
            "KAFKA_BOOTSTRAP_SERVERS": "kafka.kafka.svc.cluster.local:9092",
        }
    )


def test_normalize_payload_extracts_labels_entities_and_ids() -> None:
    raw_payload = (ROOT / "tests/fixtures/grafana_webhook_payload.json").read_bytes()
    payload = GrafanaWebhookPayload.model_validate_json(raw_payload)
    playbooks = load_playbooks(ROOT / "config/playbooks")
    received_at = datetime(2026, 3, 14, 10, 5, tzinfo=UTC)

    jobs, accepted = normalize_payload(
        payload,
        raw_payload_hash="payload-hash",
        settings=build_settings(),
        playbooks=playbooks,
        received_at=received_at,
    )

    assert len(jobs) == 1
    assert len(accepted) == 1

    job = jobs[0]
    assert job.playbook_id == "request_volume_anomaly"
    assert job.alert.alert_name == "Request Volume Anomaly"
    assert job.alert.environment == "production"
    assert job.alert.service == "edge"
    assert job.alert.severity == "critical"
    assert job.alert.datasource == "elasticsearch"
    assert job.entity_hints.ip_addresses == ["203.0.113.10"]
    assert job.entity_hints.routes == ["/critical-path"]
    assert job.entity_hints.device_ids == ["device-123"]
    assert job.entity_hints.session_ids == ["session-xyz"]
    assert job.entity_hints.asns == [64512]
    assert job.time_window.start.isoformat() == "2026-03-14T09:50:00+00:00"
    assert job.time_window.end.isoformat() == "2026-03-14T10:05:00+00:00"
    assert job.time_window.baseline_start.isoformat() == "2026-03-14T08:20:00+00:00"
    assert job.time_window.baseline_end.isoformat() == "2026-03-14T09:50:00+00:00"


def test_normalize_payload_is_deterministic_for_same_input() -> None:
    raw_payload = (ROOT / "tests/fixtures/grafana_webhook_payload.json").read_bytes()
    payload = GrafanaWebhookPayload.model_validate(json.loads(raw_payload))
    playbooks = load_playbooks(ROOT / "config/playbooks")
    received_at = datetime(2026, 3, 14, 10, 5, tzinfo=UTC)

    jobs_a, _ = normalize_payload(
        payload,
        raw_payload_hash="payload-hash",
        settings=build_settings(),
        playbooks=playbooks,
        received_at=received_at,
    )
    jobs_b, _ = normalize_payload(
        payload,
        raw_payload_hash="payload-hash",
        settings=build_settings(),
        playbooks=playbooks,
        received_at=received_at,
    )

    assert jobs_a[0].incident_id == jobs_b[0].incident_id
    assert jobs_a[0].job_id == jobs_b[0].job_id


def test_normalize_payload_uses_annotation_fallbacks_and_uri_query_entities() -> None:
    payload = GrafanaWebhookPayload.model_validate(
        {
            "receiver": "investigations",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "route_uri": "/critical-path?account_id=acct-780861&device_id=device-123",
                        "src_ip": "203.0.113.10",
                        "asn": "AS64512",
                        "user-agent": "Mozilla/5.0",
                    },
                    "annotations": {
                        "alert_name": "Request Volume Anomaly",
                        "environment": "production",
                        "service": "edge",
                        "severity": "critical",
                        "datasource": "elasticsearch",
                        "session_id": "session-xyz",
                    },
                    "startsAt": "2026-03-14T10:00:00Z",
                    "endsAt": "2026-03-14T10:20:00Z",
                    "fingerprint": "annotated-alert",
                }
            ],
        }
    )
    playbooks = load_playbooks(ROOT / "config/playbooks")
    received_at = datetime(2026, 3, 14, 10, 5, tzinfo=UTC)

    jobs, _ = normalize_payload(
        payload,
        raw_payload_hash="payload-hash",
        settings=build_settings(),
        playbooks=playbooks,
        received_at=received_at,
    )

    job = jobs[0]
    assert job.alert.alert_name == "Request Volume Anomaly"
    assert job.alert.environment == "production"
    assert job.alert.service == "edge"
    assert job.alert.severity == "critical"
    assert job.alert.datasource == "elasticsearch"
    assert job.entity_hints.routes == ["/critical-path"]
    assert job.entity_hints.account_ids == ["acct-780861"]
    assert job.entity_hints.device_ids == ["device-123"]
    assert job.entity_hints.user_agents == ["Mozilla/5.0"]
    assert job.entity_hints.session_ids == ["session-xyz"]


def test_normalize_payload_selects_availability_drop_playbook() -> None:
    payload = GrafanaWebhookPayload.model_validate(
        {
            "receiver": "investigations",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "ED-002 Availability Drop",
                        "severity": "critical",
                    },
                    "annotations": {
                        "summary": "Total request count dropped below p50 baseline — possible ingestion or availability gap",
                    },
                    "startsAt": "2026-03-14T10:00:00Z",
                    "fingerprint": "cf002",
                }
            ],
        }
    )
    playbooks = load_playbooks(ROOT / "config/playbooks")
    jobs, _ = normalize_payload(
        payload,
        raw_payload_hash="payload-hash",
        settings=build_settings(),
        playbooks=playbooks,
        received_at=datetime(2026, 3, 14, 10, 5, tzinfo=UTC),
    )

    assert jobs[0].playbook_id == "availability_drop_triage"


def test_normalize_payload_selects_source_concentration_playbook_and_extracts_ip() -> None:
    payload = GrafanaWebhookPayload.model_validate(
        {
            "receiver": "investigations",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "ED-034 · Source Entity Concentration",
                        "ClientIP.keyword": "86.51.158.196",
                        "severity": "critical",
                    },
                    "annotations": {
                        "summary": "Single IP presenting excessive device-UIDs — source concentration anomaly detected",
                    },
                    "startsAt": "2026-03-14T10:00:00Z",
                    "fingerprint": "cf034",
                }
            ],
        }
    )
    playbooks = load_playbooks(ROOT / "config/playbooks")
    jobs, _ = normalize_payload(
        payload,
        raw_payload_hash="payload-hash",
        settings=build_settings(),
        playbooks=playbooks,
        received_at=datetime(2026, 3, 14, 10, 5, tzinfo=UTC),
    )

    assert jobs[0].playbook_id == "source_entity_concentration"
    assert jobs[0].entity_hints.ip_addresses == ["86.51.158.196"]


def test_normalize_payload_anchors_firing_alerts_to_received_time() -> None:
    raw_payload = (ROOT / "tests/fixtures/grafana_webhook_payload.json").read_bytes()
    payload = GrafanaWebhookPayload.model_validate_json(raw_payload)
    playbooks = load_playbooks(ROOT / "config/playbooks")

    jobs, _ = normalize_payload(
        payload,
        raw_payload_hash="payload-hash",
        settings=build_settings(),
        playbooks=playbooks,
        received_at=datetime(2026, 3, 14, 10, 25, tzinfo=UTC),
    )

    assert jobs[0].time_window.start.isoformat() == "2026-03-14T10:10:00+00:00"
    assert jobs[0].time_window.end.isoformat() == "2026-03-14T10:25:00+00:00"
    assert jobs[0].time_window.baseline_start.isoformat() == "2026-03-14T08:40:00+00:00"
    assert jobs[0].time_window.baseline_end.isoformat() == "2026-03-14T10:10:00+00:00"


def test_normalize_payload_anchors_resolved_alerts_to_ends_at() -> None:
    payload = GrafanaWebhookPayload.model_validate(
        {
            "receiver": "investigations",
            "status": "resolved",
            "alerts": [
                {
                    "status": "resolved",
                    "labels": {
                        "alertname": "Request Volume Anomaly",
                        "service": "edge",
                    },
                    "startsAt": "2026-03-14T10:00:00Z",
                    "endsAt": "2026-03-14T10:40:00Z",
                    "fingerprint": "resolved-request-volume",
                }
            ],
        }
    )
    playbooks = load_playbooks(ROOT / "config/playbooks")

    jobs, _ = normalize_payload(
        payload,
        raw_payload_hash="payload-hash",
        settings=build_settings(),
        playbooks=playbooks,
        received_at=datetime(2026, 3, 14, 11, 0, tzinfo=UTC),
    )

    assert jobs[0].time_window.start.isoformat() == "2026-03-14T10:25:00+00:00"
    assert jobs[0].time_window.end.isoformat() == "2026-03-14T10:40:00+00:00"
