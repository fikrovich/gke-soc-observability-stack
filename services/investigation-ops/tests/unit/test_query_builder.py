from __future__ import annotations

from datetime import UTC, datetime

from app.integrations.elastic.query_builder import build_query_pack
from app.models.investigation import AlertMetadata, EntityHints, InvestigationJob, InvestigationTimeWindow
from app.models.playbook import PlaybookConfig


def test_build_query_pack_uses_entity_hint_filters_for_device_alerts() -> None:
    playbook = PlaybookConfig.model_validate(
        {
            "id": "identity_rotation_anomaly",
            "description": "test",
            "analysis_mode": "identity_rotation_anomaly",
            "match": {},
            "window": {"lookback_minutes": 60, "lookahead_minutes": 5},
            "baseline": {"window_minutes": 60, "offset_windows": 6},
            "filters": [
                {"canonical_field": "device_id", "operator": "entity_hint", "required": True}
            ],
            "field_mappings": {
                "timestamp": "@timestamp",
                "client_ip": "ClientIP.keyword",
                "device_id": "RequestHeaders.device-uid.keyword",
                "session_id": "RequestHeaders.session-id.keyword",
            },
            "feature_flags": {
                "device_concentration": True,
                "client_hint_concentration": False,
                "session_concentration": False,
                "unique_ips_per_device": True,
            },
        }
    )
    job = InvestigationJob(
        job_id="job-1",
        incident_id="incident-1",
        received_at=datetime(2026, 3, 14, 10, 5, tzinfo=UTC),
        alert=AlertMetadata(
            status="firing",
            alert_name="ED-035 · Device IP Hopping",
            fingerprint="fingerprint-1",
            starts_at=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
        ),
        time_window=InvestigationTimeWindow(
            start=datetime(2026, 3, 14, 9, 0, tzinfo=UTC),
            end=datetime(2026, 3, 14, 10, 5, tzinfo=UTC),
            baseline_start=datetime(2026, 3, 14, 3, 0, tzinfo=UTC),
            baseline_end=datetime(2026, 3, 14, 9, 0, tzinfo=UTC),
            baseline_windows=6,
        ),
        entity_hints=EntityHints(device_ids=["device-123"]),
        playbook_id="identity_rotation_anomaly",
        fingerprint="fingerprint-1",
        raw_payload_hash="hash",
    )

    query_pack = build_query_pack(job, playbook, max_terms_bucket_size=10)

    filters = query_pack.alert_query["query"]["bool"]["filter"]
    assert {"term": {"RequestHeaders.device-uid.keyword": "device-123"}} in filters
    assert "unique_accounts_per_ip" in query_pack.unavailable_features
    assert "unique_ips_per_device" not in query_pack.unavailable_features
