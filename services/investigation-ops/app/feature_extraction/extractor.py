from __future__ import annotations

from app.integrations.elastic.query_builder import QueryPack
from app.models.investigation import (
    ConcentrationFeature,
    DistributionBucket,
    InvestigationFeatures,
    PairwiseCardinalityFeature,
    VolumeDeltaFeature,
)
from app.models.playbook import PlaybookConfig


def extract_features(
    *,
    playbook: PlaybookConfig,
    query_pack: QueryPack,
    alert_response: dict,
    baseline_response: dict,
) -> InvestigationFeatures:
    current_count = int(alert_response.get("hits", {}).get("total", {}).get("value", 0))
    baseline_buckets = (
        baseline_response.get("aggregations", {})
        .get("requests_over_time", {})
        .get("buckets", [])
    )
    baseline_total = sum(int(bucket.get("doc_count", 0)) for bucket in baseline_buckets)
    baseline_average = (
        baseline_total / playbook.baseline.offset_windows
        if playbook.baseline.offset_windows
        else 0.0
    )
    delta = float(current_count) - baseline_average
    ratio = None
    if baseline_average > 0:
        ratio = float(current_count) / baseline_average

    aggregations = alert_response.get("aggregations", {})

    return InvestigationFeatures(
        request_count_delta=VolumeDeltaFeature(
            current_count=current_count,
            baseline_average=baseline_average,
            delta=delta,
            ratio=ratio,
        ),
        top_ip_concentration=_concentration_feature(aggregations, "top_ips", current_count, "client_ip"),
        top_asn_concentration=_concentration_feature(aggregations, "top_asns", current_count, "asn"),
        top_user_agent_concentration=_concentration_feature(
            aggregations,
            "top_user_agents",
            current_count,
            "user_agent",
        ),
        response_status_distribution=_distribution_feature(
            aggregations,
            "response_status",
            current_count,
        ),
        challenge_outcome_distribution=_distribution_feature(
            aggregations,
            "challenge_outcomes",
            current_count,
        ),
        security_action_concentration=_concentration_feature(
            aggregations,
            "security_actions",
            current_count,
            "security_action",
        ),
        security_rule_concentration=_concentration_feature(
            aggregations,
            "security_rules",
            current_count,
            "security_rule_description",
        ),
        path_concentration=_concentration_feature(aggregations, "top_paths", current_count, "path"),
        device_concentration=_concentration_feature(
            aggregations,
            "top_devices",
            current_count,
            "device_id",
        ),
        client_hint_concentration=_concentration_feature(
            aggregations,
            "top_client_hints",
            current_count,
            "client_hint",
        ),
        session_concentration=_concentration_feature(
            aggregations,
            "top_sessions",
            current_count,
            "session_id",
        ),
        unique_accounts_per_ip=_cardinality_feature(
            aggregations,
            "accounts_per_ip",
            "client_ip",
            "account_id",
        ),
        unique_devices_per_account=_cardinality_feature(
            aggregations,
            "devices_per_account",
            "account_id",
            "device_id",
        ),
        unique_devices_per_ip=_cardinality_feature(
            aggregations,
            "devices_per_ip",
            "client_ip",
            "device_id",
        ),
        unique_ips_per_device=_cardinality_feature(
            aggregations,
            "ips_per_device",
            "device_id",
            "client_ip",
        ),
        unique_ips_per_session=_cardinality_feature(
            aggregations,
            "ips_per_session",
            "session_id",
            "client_ip",
        ),
        new_account_ratio=_new_account_ratio(aggregations),
        unavailable_features=sorted(set(query_pack.unavailable_features)),
    )


def _distribution_feature(aggregations: dict, name: str, total: int) -> list[DistributionBucket]:
    buckets = aggregations.get(name, {}).get("buckets", [])
    return [_bucket_from_agg(bucket, total) for bucket in buckets]


def _concentration_feature(
    aggregations: dict,
    name: str,
    total: int,
    field: str,
) -> ConcentrationFeature | None:
    buckets = aggregations.get(name, {}).get("buckets")
    if not buckets:
        return None
    distribution = [_bucket_from_agg(bucket, total) for bucket in buckets]
    top = distribution[0]
    return ConcentrationFeature(
        field=field,
        top_value=top.key,
        top_count=top.count,
        ratio=top.ratio,
        buckets=distribution,
    )


def _cardinality_feature(
    aggregations: dict,
    name: str,
    entity_field: str,
    cardinality_field: str,
) -> PairwiseCardinalityFeature | None:
    buckets = aggregations.get(name, {}).get("buckets")
    if not buckets:
        return None
    return PairwiseCardinalityFeature(
        entity_field=entity_field,
        cardinality_field=cardinality_field,
        buckets=[
            {
                "entity_value": str(bucket.get("key", "")),
                "doc_count": int(bucket.get("doc_count", 0)),
                "unique_count": int(
                    bucket.get("unique_values", {}).get("value", 0)
                ),
            }
            for bucket in buckets
        ],
    )


def _new_account_ratio(aggregations: dict) -> float | None:
    observed_accounts = int(aggregations.get("observed_accounts", {}).get("value", 0))
    if observed_accounts <= 0:
        return None
    new_accounts = int(
        aggregations.get("new_accounts", {})
        .get("count", {})
        .get("value", 0)
    )
    return new_accounts / observed_accounts


def _bucket_from_agg(bucket: dict, total: int) -> DistributionBucket:
    count = int(bucket.get("doc_count", 0))
    ratio = (count / total) if total > 0 else 0.0
    return DistributionBucket(key=str(bucket.get("key")), count=count, ratio=ratio)
