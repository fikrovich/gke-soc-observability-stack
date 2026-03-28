from __future__ import annotations

from datetime import UTC, datetime

from app.integrations.slack.formatter import build_slack_payload
from app.models.investigation import (
    AlertMetadata,
    InvestigationFeatures,
    InvestigationResult,
    InvestigationTimeWindow,
    NotificationStatus,
    ProcessingStatus,
    RecommendedQuery,
    TopSuspiciousEntity,
    VolumeDeltaFeature,
)


def test_build_slack_payload_contains_core_summary() -> None:
    result = InvestigationResult(
        incident_id="incident-123",
        job_id="job-123",
        source_index_alias="edge-logs",
        alert_metadata=AlertMetadata(
            status="firing",
            alert_name="Request Volume Anomaly",
            environment="production",
            service="edge",
            severity="critical",
            datasource="elasticsearch",
            fingerprint="abcd1234",
            starts_at=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
            labels={},
            annotations={},
            values={},
        ),
        time_window=InvestigationTimeWindow(
            start=datetime(2026, 3, 14, 9, 45, tzinfo=UTC),
            end=datetime(2026, 3, 14, 10, 15, tzinfo=UTC),
            baseline_start=datetime(2026, 3, 14, 8, 15, tzinfo=UTC),
            baseline_end=datetime(2026, 3, 14, 9, 45, tzinfo=UTC),
            baseline_windows=6,
        ),
        playbook_id="request_volume_anomaly",
        extracted_features=InvestigationFeatures(
            request_count_delta=VolumeDeltaFeature(
                current_count=900,
                baseline_average=100,
                delta=800,
                ratio=9.0,
            )
        ),
        top_suspicious_entities=[
            TopSuspiciousEntity(
                entity_type="client_ip",
                value="203.0.113.10",
                count=450,
                ratio=0.5,
                evidence="client_ip dominates the alert window",
            )
        ],
        evidence_summary=["Request volume is 9.00x baseline."],
        preliminary_abuse_type_hypothesis="generic_triage",
        confidence=0.71,
        recommended_next_queries=[
            RecommendedQuery(
                description="Review dominant IP activity",
                kql='ClientIP.keyword:"203.0.113.10" and ClientRequestPath.keyword:"/critical-path"',
            )
        ],
        recommended_mitigations=["Apply targeted rate limits."],
        notification_status=NotificationStatus.sent,
        processing_status=ProcessingStatus.completed,
        processed_at=datetime(2026, 3, 14, 10, 6, tzinfo=UTC),
    )

    payload = build_slack_payload(result)

    assert payload["text"].startswith("[critical] Request Volume Anomaly")
    assert len(payload["blocks"]) == 5
    assert "incident-123" in payload["blocks"][1]["text"]["text"]

