from __future__ import annotations

from app.feature_extraction.extractor import extract_features
from app.integrations.elastic.query_builder import QueryPack
from app.models.playbook import PlaybookConfig
from app.scoring.hypothesis import score_investigation


def test_score_investigation_handles_request_volume_anomaly() -> None:
    playbook = PlaybookConfig.model_validate(
        {
            "id": "request_volume_anomaly",
            "description": "test",
            "analysis_mode": "generic_triage",
            "match": {},
            "window": {"lookback_minutes": 15, "lookahead_minutes": 15},
            "baseline": {"window_minutes": 15, "offset_windows": 6},
            "field_mappings": {
                "timestamp": "@timestamp",
                "client_ip": "ClientIP.keyword",
                "path": "ClientRequestPath.keyword",
                "asn": "ClientASN",
                "device_id": "RequestHeaders.device-uid.keyword",
                "account_id": "RequestHeaders.account-id.keyword",
                "client_hint": "RequestHeaders.client-id.keyword",
                "session_id": "RequestHeaders.session-id.keyword",
                "security_action": "SecurityAction.keyword"
            },
            "recommended_query_templates": [
                "{client_ip_field}:\"{top_ip}\" and {path_field}:\"{top_path}\"",
                "{account_id_field}:\"{top_account_id}\" and {path_field}:\"{top_path}\""
            ],
            "recommended_mitigations": ["Apply scoped rate limits after validating the route-level anomaly."]
        }
    )
    query_pack = QueryPack(alert_query={}, baseline_query={}, field_mappings=playbook.field_mappings)
    features = extract_features(
        playbook=playbook,
        query_pack=query_pack,
        alert_response={
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
                "top_sessions": {"buckets": [{"key": "session-xyz", "doc_count": 500}]},
                "accounts_per_ip": {
                    "buckets": [
                        {
                            "key": "203.0.113.10",
                            "doc_count": 450,
                            "unique_values": {"value": 12},
                        }
                    ]
                },
                "devices_per_account": {
                    "buckets": [
                        {
                            "key": "780861",
                            "doc_count": 300,
                            "unique_values": {"value": 4},
                        }
                    ]
                },
            }
        },
        baseline_response={
            "aggregations": {
                "requests_over_time": {
                    "buckets": [{"doc_count": 100}] * 6
                }
            }
        },
    )

    outcome = score_investigation(
        playbook=playbook,
        features=features,
        field_mappings=playbook.field_mappings,
    )

    assert outcome.hypothesis == "generic_triage"
    assert outcome.confidence >= 0.6
    assert outcome.recommended_next_queries
    assert any("Top IP touched 12 unique accounts." in item for item in outcome.evidence_summary)
    assert any("Top account touched 4 unique devices." in item for item in outcome.evidence_summary)
    assert any("780861" in item.kql for item in outcome.recommended_next_queries)
    assert outcome.recommended_mitigations == ["Apply scoped rate limits after validating the route-level anomaly."]


def test_score_investigation_identifies_availability_drop_triage() -> None:
    playbook = PlaybookConfig.model_validate(
        {
            "id": "availability_drop_triage",
            "description": "test",
            "analysis_mode": "traffic_drop",
            "match": {},
            "window": {"lookback_minutes": 5, "lookahead_minutes": 5},
            "baseline": {"window_minutes": 5, "offset_windows": 12},
            "field_mappings": {
                "timestamp": "@timestamp",
                "client_ip": "ClientIP.keyword",
                "path": "ClientRequestPath.keyword",
                "edge_status": "EdgeResponseStatus",
                "origin_status": "OriginResponseStatus",
                "security_action": "SecurityAction.keyword",
            },
            "recommended_query_templates": [
                "{path_field}:*",
                "{edge_status_field}:*",
            ],
            "recommended_mitigations": ["Validate Edge and upstream traffic flow."],
        }
    )
    query_pack = QueryPack(alert_query={}, baseline_query={}, field_mappings=playbook.field_mappings)
    features = extract_features(
        playbook=playbook,
        query_pack=query_pack,
        alert_response={
            "hits": {"total": {"value": 0}},
            "aggregations": {
                "response_status": {"buckets": []},
                "top_paths": {"buckets": []},
                "top_ips": {"buckets": []},
            },
        },
        baseline_response={
            "aggregations": {
                "requests_over_time": {
                    "buckets": [{"doc_count": 1827709}] * 12
                }
            }
        },
    )

    outcome = score_investigation(
        playbook=playbook,
        features=features,
        field_mappings=playbook.field_mappings,
    )

    assert outcome.hypothesis == "traffic_drop_or_ingestion_gap"
    assert outcome.confidence >= 0.9
    assert any("Observed volume is 0.00% of baseline." in item for item in outcome.evidence_summary)
    assert outcome.recommended_next_queries
