from __future__ import annotations

from app.feature_extraction.extractor import extract_features
from app.integrations.elastic.query_builder import QueryPack
from app.models.playbook import PlaybookConfig


def test_extract_features_computes_volume_and_concentration_metrics() -> None:
    playbook = PlaybookConfig.model_validate(
        {
            "id": "request_volume_anomaly",
            "description": "test",
            "match": {},
            "window": {"lookback_minutes": 15, "lookahead_minutes": 15},
            "baseline": {"window_minutes": 15, "offset_windows": 6},
            "field_mappings": {"timestamp": "@timestamp"},
        }
    )
    query_pack = QueryPack(
        alert_query={},
        baseline_query={},
        field_mappings={"timestamp": "@timestamp"},
        unavailable_features=["new_account_ratio"],
    )
    alert_response = {
        "hits": {"total": {"value": 900}},
        "aggregations": {
            "top_ips": {"buckets": [{"key": "203.0.113.10", "doc_count": 450}]},
            "top_asns": {"buckets": [{"key": 64512, "doc_count": 600}]},
            "top_user_agents": {"buckets": [{"key": "Mozilla/5.0", "doc_count": 500}]},
            "response_status": {
                "buckets": [
                    {"key": 403, "doc_count": 400},
                    {"key": 200, "doc_count": 300},
                    {"key": 429, "doc_count": 200}
                ]
            },
            "security_actions": {"buckets": [{"key": "challenge", "doc_count": 300}]},
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
    }
    baseline_response = {
        "aggregations": {
            "requests_over_time": {
                "buckets": [
                    {"key_as_string": "1", "doc_count": 100},
                    {"key_as_string": "2", "doc_count": 120},
                    {"key_as_string": "3", "doc_count": 110},
                    {"key_as_string": "4", "doc_count": 90},
                    {"key_as_string": "5", "doc_count": 80},
                    {"key_as_string": "6", "doc_count": 100}
                ]
            }
        }
    }

    features = extract_features(
        playbook=playbook,
        query_pack=query_pack,
        alert_response=alert_response,
        baseline_response=baseline_response,
    )

    assert features.request_count_delta.current_count == 900
    assert features.request_count_delta.baseline_average == 100
    assert features.request_count_delta.delta == 800
    assert features.request_count_delta.ratio == 9
    assert features.top_ip_concentration is not None
    assert features.top_ip_concentration.top_value == "203.0.113.10"
    assert round(features.top_ip_concentration.ratio, 2) == 0.50
    assert features.path_concentration is not None
    assert round(features.path_concentration.ratio, 2) == 0.78
    assert features.response_status_distribution[0].key == "403"
    assert features.unique_accounts_per_ip is not None
    assert features.unique_accounts_per_ip.buckets[0]["entity_value"] == "203.0.113.10"
    assert features.unique_accounts_per_ip.buckets[0]["unique_count"] == 12
    assert features.unique_devices_per_account is not None
    assert features.unique_devices_per_account.buckets[0]["entity_value"] == "780861"
    assert features.unique_devices_per_account.buckets[0]["unique_count"] == 4
    assert features.unavailable_features == ["new_account_ratio"]
