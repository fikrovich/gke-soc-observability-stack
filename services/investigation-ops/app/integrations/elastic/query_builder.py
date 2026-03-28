from __future__ import annotations

from dataclasses import dataclass, field

from app.models.investigation import InvestigationJob
from app.models.playbook import PlaybookConfig, PlaybookFilter


@dataclass(slots=True)
class QueryPack:
    alert_query: dict
    baseline_query: dict
    field_mappings: dict[str, str]
    unavailable_features: list[str] = field(default_factory=list)


def build_query_pack(
    job: InvestigationJob,
    playbook: PlaybookConfig,
    *,
    max_terms_bucket_size: int,
) -> QueryPack:
    field_mappings = dict(playbook.field_mappings)
    timestamp_field = field_mappings["timestamp"]
    base_filters = [_translate_filter(item, field_mappings, job) for item in playbook.filters]
    base_filters = [item for item in base_filters if item]

    alert_query: dict = {
        "size": 0,
        "track_total_hits": True,
        "query": {
            "bool": {
                "filter": [
                    *base_filters,
                    {
                        "range": {
                            timestamp_field: {
                                "gte": job.time_window.start.isoformat(),
                                "lt": job.time_window.end.isoformat(),
                            }
                        }
                    },
                ]
            }
        },
        "aggs": {},
    }

    baseline_query: dict = {
        "size": 0,
        "track_total_hits": True,
        "query": {
            "bool": {
                "filter": [
                    *base_filters,
                    {
                        "range": {
                            timestamp_field: {
                                "gte": job.time_window.baseline_start.isoformat(),
                                "lt": job.time_window.baseline_end.isoformat(),
                            }
                        }
                    },
                ]
            }
        },
        "aggs": {
            "requests_over_time": {
                "date_histogram": {
                    "field": timestamp_field,
                    "fixed_interval": f"{playbook.baseline.window_minutes}m",
                    "min_doc_count": 0,
                }
            }
        },
    }

    unavailable_features: list[str] = []

    _add_terms_agg(alert_query, field_mappings, "client_ip", "top_ips", max_terms_bucket_size, unavailable_features, "top_ip_concentration")
    _add_terms_agg(alert_query, field_mappings, "asn", "top_asns", max_terms_bucket_size, unavailable_features, "top_asn_concentration")
    _add_terms_agg(alert_query, field_mappings, "user_agent", "top_user_agents", max_terms_bucket_size, unavailable_features, "top_user_agent_concentration")
    _add_terms_agg(alert_query, field_mappings, "edge_status", "response_status", max_terms_bucket_size, unavailable_features, "response_status_distribution")
    _add_terms_agg(alert_query, field_mappings, "challenge_outcome", "challenge_outcomes", max_terms_bucket_size, unavailable_features, "challenge_outcome_distribution", enabled=playbook.feature_flags.challenge_outcome_distribution)
    _add_terms_agg(alert_query, field_mappings, "security_action", "security_actions", max_terms_bucket_size, unavailable_features, "security_action_concentration")
    _add_terms_agg(alert_query, field_mappings, "security_rule_description", "security_rules", max_terms_bucket_size, unavailable_features, "security_rule_concentration")
    _add_terms_agg(alert_query, field_mappings, "path", "top_paths", max_terms_bucket_size, unavailable_features, "path_concentration")
    _add_terms_agg(alert_query, field_mappings, "device_id", "top_devices", max_terms_bucket_size, unavailable_features, "device_concentration", enabled=playbook.feature_flags.device_concentration)
    _add_terms_agg(alert_query, field_mappings, "client_hint", "top_client_hints", max_terms_bucket_size, unavailable_features, "client_hint_concentration", enabled=playbook.feature_flags.client_hint_concentration)
    _add_terms_agg(alert_query, field_mappings, "session_id", "top_sessions", max_terms_bucket_size, unavailable_features, "session_concentration", enabled=playbook.feature_flags.session_concentration)

    _add_cardinality_terms_agg(
        alert_query,
        field_mappings,
        "client_ip",
        "account_id",
        "accounts_per_ip",
        max_terms_bucket_size,
        unavailable_features,
        "unique_accounts_per_ip",
        enabled=playbook.feature_flags.unique_accounts_per_ip,
    )
    _add_cardinality_terms_agg(
        alert_query,
        field_mappings,
        "account_id",
        "device_id",
        "devices_per_account",
        max_terms_bucket_size,
        unavailable_features,
        "unique_devices_per_account",
        enabled=playbook.feature_flags.unique_devices_per_account,
    )
    _add_cardinality_terms_agg(
        alert_query,
        field_mappings,
        "client_ip",
        "device_id",
        "devices_per_ip",
        max_terms_bucket_size,
        unavailable_features,
        "unique_devices_per_ip",
        enabled=playbook.feature_flags.unique_devices_per_ip,
    )
    _add_cardinality_terms_agg(
        alert_query,
        field_mappings,
        "device_id",
        "client_ip",
        "ips_per_device",
        max_terms_bucket_size,
        unavailable_features,
        "unique_ips_per_device",
        enabled=playbook.feature_flags.unique_ips_per_device,
    )
    _add_cardinality_terms_agg(
        alert_query,
        field_mappings,
        "session_id",
        "client_ip",
        "ips_per_session",
        max_terms_bucket_size,
        unavailable_features,
        "unique_ips_per_session",
        enabled=playbook.feature_flags.unique_ips_per_session,
    )
    _add_new_account_ratio_aggs(
        alert_query,
        field_mappings,
        unavailable_features,
        enabled=playbook.feature_flags.new_account_ratio,
        start=job.time_window.start.isoformat(),
        end=job.time_window.end.isoformat(),
    )

    return QueryPack(
        alert_query=alert_query,
        baseline_query=baseline_query,
        field_mappings=field_mappings,
        unavailable_features=unavailable_features,
    )


def _translate_filter(
    filter_config: PlaybookFilter,
    field_mappings: dict[str, str],
    job: InvestigationJob,
) -> dict | None:
    field_name = field_mappings.get(filter_config.canonical_field)
    if not field_name:
        return None

    operator = filter_config.operator
    if operator == "term":
        return {"term": {field_name: filter_config.value}}
    if operator == "terms":
        return {"terms": {field_name: filter_config.values}}
    if operator == "prefix":
        return {"prefix": {field_name: str(filter_config.value)}}
    if operator == "wildcard":
        return {"wildcard": {field_name: {"value": str(filter_config.value)}}}
    if operator == "exists":
        return {"exists": {"field": field_name}}
    if operator == "entity_hint":
        values = _entity_hint_values(job, filter_config.canonical_field)
        if not values:
            if filter_config.required:
                raise ValueError(f"missing required entity hint for {filter_config.canonical_field}")
            return None
        if len(values) == 1:
            return {"term": {field_name: values[0]}}
        return {"terms": {field_name: values}}
    raise ValueError(f"unsupported playbook filter operator: {operator}")


def _entity_hint_values(job: InvestigationJob, canonical_field: str) -> list[str | int]:
    if canonical_field == "client_ip":
        return list(job.entity_hints.ip_addresses)
    if canonical_field in {"path", "uri"}:
        return list(job.entity_hints.routes)
    if canonical_field == "account_id":
        return list(job.entity_hints.account_ids)
    if canonical_field == "device_id":
        return list(job.entity_hints.device_ids)
    if canonical_field == "asn":
        return list(job.entity_hints.asns)
    if canonical_field == "user_agent":
        return list(job.entity_hints.user_agents)
    if canonical_field == "client_hint":
        return list(job.entity_hints.client_ids)
    if canonical_field == "session_id":
        return list(job.entity_hints.session_ids)
    return []


def _add_terms_agg(
    query: dict,
    field_mappings: dict[str, str],
    canonical_field: str,
    agg_name: str,
    bucket_size: int,
    unavailable_features: list[str],
    feature_name: str,
    *,
    enabled: bool = True,
) -> None:
    if not enabled:
        unavailable_features.append(feature_name)
        return
    field_name = field_mappings.get(canonical_field)
    if not field_name:
        unavailable_features.append(feature_name)
        return
    query["aggs"][agg_name] = {"terms": {"field": field_name, "size": bucket_size}}


def _add_cardinality_terms_agg(
    query: dict,
    field_mappings: dict[str, str],
    entity_field: str,
    cardinality_field: str,
    agg_name: str,
    bucket_size: int,
    unavailable_features: list[str],
    feature_name: str,
    *,
    enabled: bool = True,
) -> None:
    if not enabled:
        unavailable_features.append(feature_name)
        return
    mapped_entity = field_mappings.get(entity_field)
    mapped_cardinality = field_mappings.get(cardinality_field)
    if not mapped_entity or not mapped_cardinality:
        unavailable_features.append(feature_name)
        return
    query["aggs"][agg_name] = {
        "terms": {"field": mapped_entity, "size": bucket_size},
        "aggs": {"unique_values": {"cardinality": {"field": mapped_cardinality}}},
    }


def _add_new_account_ratio_aggs(
    query: dict,
    field_mappings: dict[str, str],
    unavailable_features: list[str],
    *,
    enabled: bool,
    start: str,
    end: str,
) -> None:
    if not enabled:
        unavailable_features.append("new_account_ratio")
        return

    account_id_field = field_mappings.get("account_id")
    account_created_field = field_mappings.get("account_created_at")
    if not account_id_field or not account_created_field:
        unavailable_features.append("new_account_ratio")
        return

    query["aggs"]["observed_accounts"] = {
        "cardinality": {"field": account_id_field}
    }
    query["aggs"]["new_accounts"] = {
        "filter": {
            "range": {
                account_created_field: {
                    "gte": start,
                    "lt": end,
                }
            }
        },
        "aggs": {"count": {"cardinality": {"field": account_id_field}}},
    }
