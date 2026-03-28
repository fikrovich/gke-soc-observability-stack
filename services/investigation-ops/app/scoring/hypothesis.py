from __future__ import annotations

from dataclasses import dataclass, field
from string import Formatter

from app.models.investigation import (
    ConcentrationFeature,
    InvestigationFeatures,
    PairwiseCardinalityFeature,
    RecommendedQuery,
    TopSuspiciousEntity,
)
from app.models.playbook import PlaybookConfig


@dataclass(slots=True)
class ScoringOutcome:
    hypothesis: str
    confidence: float
    evidence_summary: list[str] = field(default_factory=list)
    top_suspicious_entities: list[TopSuspiciousEntity] = field(default_factory=list)
    recommended_next_queries: list[RecommendedQuery] = field(default_factory=list)
    recommended_mitigations: list[str] = field(default_factory=list)


def score_investigation(
    *,
    playbook: PlaybookConfig,
    features: InvestigationFeatures,
    field_mappings: dict[str, str],
) -> ScoringOutcome:
    mode = playbook.analysis_mode
    if mode == "traffic_drop":
        return _score_traffic_drop(playbook, features, field_mappings)
    if mode == "device_farming":
        return _score_device_farming(playbook, features, field_mappings)
    if mode == "device_ip_hopping":
        return _score_device_ip_hopping(playbook, features, field_mappings)
    if mode == "session_multi_ip":
        return _score_session_multi_ip(playbook, features, field_mappings)
    return _score_generic_triage(playbook, features, field_mappings)


def _score_traffic_drop(
    playbook: PlaybookConfig,
    features: InvestigationFeatures,
    field_mappings: dict[str, str],
) -> ScoringOutcome:
    evidence: list[str] = []
    suspicious_entities = _collect_suspicious_entities(features, 0.8)
    volume = features.request_count_delta

    confidence = 0.25
    hypothesis = "unknown"
    if volume.baseline_average > 0:
        evidence.append(
            f"Request volume is {volume.current_count} in the alert window versus a baseline average of {volume.baseline_average:.1f}."
        )
        if volume.ratio is not None:
            evidence.append(f"Observed volume is {volume.ratio:.2%} of baseline.")
            if volume.current_count == 0 and volume.baseline_average >= 100000:
                hypothesis = "traffic_drop_or_ingestion_gap"
                confidence = 0.95
            elif volume.ratio <= 0.10:
                hypothesis = "traffic_drop_or_ingestion_gap"
                confidence = 0.85
            elif volume.ratio <= 0.25:
                hypothesis = "traffic_drop_or_ingestion_gap"
                confidence = 0.70
    elif volume.current_count == 0:
        evidence.append("No requests were observed in the alert window.")
        hypothesis = "traffic_drop_or_ingestion_gap"
        confidence = 0.60

    if features.top_ip_concentration and features.top_ip_concentration.top_count > 0:
        evidence.append(
            f"Traffic that remains is concentrated on {features.top_ip_concentration.top_value} at {features.top_ip_concentration.ratio:.2%}."
        )
    if features.path_concentration and features.path_concentration.top_count > 0:
        evidence.append(
            f"Remaining traffic is concentrated on {features.path_concentration.top_value} at {features.path_concentration.ratio:.2%}."
        )
    if features.response_status_distribution:
        dominant_status = features.response_status_distribution[0]
        evidence.append(f"Dominant response status is {dominant_status.key} at {dominant_status.ratio:.2%}.")

    _append_unavailable_features(evidence, features)
    return _build_outcome(
        playbook=playbook,
        field_mappings=field_mappings,
        features=features,
        evidence=evidence,
        suspicious_entities=suspicious_entities,
        hypothesis=hypothesis,
        confidence=confidence,
    )


def _score_device_farming(
    playbook: PlaybookConfig,
    features: InvestigationFeatures,
    field_mappings: dict[str, str],
) -> ScoringOutcome:
    evidence: list[str] = []
    suspicious_entities = _collect_suspicious_entities(features, 0.5)
    pairwise = features.unique_devices_per_ip
    top = _top_pairwise_bucket(pairwise)

    hypothesis = "unknown"
    confidence = 0.25
    if top:
        unique_devices = int(top["unique_count"])
        evidence.append(f"IP {top['entity_value']} presented {unique_devices} unique devices in the alert window.")
        suspicious = _pairwise_suspicious_entity(
            pairwise,
            evidence=f"client_ip is associated with {unique_devices} distinct device identifiers.",
        )
        if suspicious:
            suspicious_entities.insert(0, suspicious)
        if unique_devices >= 15:
            hypothesis = "device_farming"
            confidence = 0.92
        elif unique_devices >= 10:
            hypothesis = "device_farming"
            confidence = 0.78

    if features.top_user_agent_concentration:
        evidence.append(
            f"Top user-agent concentration is {features.top_user_agent_concentration.ratio:.2%}."
        )
    if features.response_status_distribution:
        dominant_status = features.response_status_distribution[0]
        evidence.append(f"Dominant response status is {dominant_status.key} at {dominant_status.ratio:.2%}.")

    _append_unavailable_features(evidence, features)
    return _build_outcome(
        playbook=playbook,
        field_mappings=field_mappings,
        features=features,
        evidence=evidence,
        suspicious_entities=suspicious_entities,
        hypothesis=hypothesis,
        confidence=confidence,
    )


def _score_device_ip_hopping(
    playbook: PlaybookConfig,
    features: InvestigationFeatures,
    field_mappings: dict[str, str],
) -> ScoringOutcome:
    evidence: list[str] = []
    suspicious_entities = _collect_suspicious_entities(features, 0.5)
    pairwise = features.unique_ips_per_device
    top = _top_pairwise_bucket(pairwise)

    hypothesis = "unknown"
    confidence = 0.25
    if top:
        unique_ips = int(top["unique_count"])
        evidence.append(f"Device {top['entity_value']} used {unique_ips} unique IPs in the alert window.")
        suspicious = _pairwise_suspicious_entity(
            pairwise,
            evidence=f"device_id is associated with {unique_ips} distinct client IP addresses.",
        )
        if suspicious:
            suspicious_entities.insert(0, suspicious)
        if unique_ips >= 30:
            hypothesis = "device_ip_hopping"
            confidence = 0.92
        elif unique_ips >= 15:
            hypothesis = "device_ip_hopping"
            confidence = 0.78

    if features.top_asn_concentration:
        evidence.append(f"Top ASN concentration is {features.top_asn_concentration.ratio:.2%}.")
    if features.response_status_distribution:
        dominant_status = features.response_status_distribution[0]
        evidence.append(f"Dominant response status is {dominant_status.key} at {dominant_status.ratio:.2%}.")

    _append_unavailable_features(evidence, features)
    return _build_outcome(
        playbook=playbook,
        field_mappings=field_mappings,
        features=features,
        evidence=evidence,
        suspicious_entities=suspicious_entities,
        hypothesis=hypothesis,
        confidence=confidence,
    )


def _score_session_multi_ip(
    playbook: PlaybookConfig,
    features: InvestigationFeatures,
    field_mappings: dict[str, str],
) -> ScoringOutcome:
    evidence: list[str] = []
    suspicious_entities = _collect_suspicious_entities(features, 0.5)
    pairwise = features.unique_ips_per_session
    top = _top_pairwise_bucket(pairwise)

    hypothesis = "unknown"
    confidence = 0.25
    if top:
        unique_ips = int(top["unique_count"])
        evidence.append(f"Session {top['entity_value']} used {unique_ips} unique IPs in the alert window.")
        suspicious = _pairwise_suspicious_entity(
            pairwise,
            evidence=f"session_id is associated with {unique_ips} distinct client IP addresses.",
        )
        if suspicious:
            suspicious_entities.insert(0, suspicious)
        if unique_ips >= 50:
            hypothesis = "session_replay_or_hijack"
            confidence = 0.95
        elif unique_ips >= 20:
            hypothesis = "session_replay_or_hijack"
            confidence = 0.82

    if features.top_user_agent_concentration:
        evidence.append(
            f"Top user-agent concentration is {features.top_user_agent_concentration.ratio:.2%}."
        )

    _append_unavailable_features(evidence, features)
    return _build_outcome(
        playbook=playbook,
        field_mappings=field_mappings,
        features=features,
        evidence=evidence,
        suspicious_entities=suspicious_entities,
        hypothesis=hypothesis,
        confidence=confidence,
    )
def _score_generic_triage(
    playbook: PlaybookConfig,
    features: InvestigationFeatures,
    field_mappings: dict[str, str],
) -> ScoringOutcome:
    evidence: list[str] = []
    suspicious_entities = _collect_suspicious_entities(features, 0.75)
    volume = features.request_count_delta

    hypothesis = "unknown"
    confidence = 0.20
    if volume.ratio and volume.ratio >= playbook.hypothesis_thresholds.request_spike_ratio_high:
        evidence.append(
            f"Request volume is {volume.ratio:.2f}x baseline ({volume.current_count} vs {volume.baseline_average:.1f})."
        )
        confidence = 0.35
    elif volume.ratio is not None and volume.ratio <= 0.25 and volume.baseline_average > 0:
        evidence.append(
            f"Request volume dropped to {volume.ratio:.2%} of baseline ({volume.current_count} vs {volume.baseline_average:.1f})."
        )
        confidence = 0.35

    if features.response_status_distribution:
        dominant_status = features.response_status_distribution[0]
        evidence.append(f"Dominant response status is {dominant_status.key} at {dominant_status.ratio:.2%}.")

    _append_unavailable_features(evidence, features)
    return _build_outcome(
        playbook=playbook,
        field_mappings=field_mappings,
        features=features,
        evidence=evidence,
        suspicious_entities=suspicious_entities,
        hypothesis=hypothesis,
        confidence=confidence,
    )


def _build_outcome(
    *,
    playbook: PlaybookConfig,
    field_mappings: dict[str, str],
    features: InvestigationFeatures,
    evidence: list[str],
    suspicious_entities: list[TopSuspiciousEntity],
    hypothesis: str,
    confidence: float,
) -> ScoringOutcome:
    return ScoringOutcome(
        hypothesis=hypothesis,
        confidence=confidence,
        evidence_summary=evidence,
        top_suspicious_entities=suspicious_entities[:6],
        recommended_next_queries=_build_recommended_queries(features, field_mappings, playbook),
        recommended_mitigations=list(playbook.recommended_mitigations),
    )


def _append_unavailable_features(evidence: list[str], features: InvestigationFeatures) -> None:
    if features.unavailable_features:
        evidence.append(f"Unavailable features: {', '.join(sorted(features.unavailable_features))}.")


def _collect_suspicious_entities(
    features: InvestigationFeatures,
    minimum_ratio: float,
) -> list[TopSuspiciousEntity]:
    candidates: list[TopSuspiciousEntity] = []
    for feature in (
        features.top_ip_concentration,
        features.top_asn_concentration,
        features.top_user_agent_concentration,
        features.path_concentration,
        features.device_concentration,
        features.client_hint_concentration,
        features.session_concentration,
    ):
        if not feature or not feature.top_value or feature.ratio < minimum_ratio:
            continue
        candidates.append(
            TopSuspiciousEntity(
                entity_type=feature.field,
                value=feature.top_value,
                count=feature.top_count,
                ratio=feature.ratio,
                evidence=f"{feature.field} dominates the alert window at {feature.ratio:.2%}.",
            )
        )
    return candidates[:6]


def _pairwise_suspicious_entity(
    feature: PairwiseCardinalityFeature | None,
    *,
    evidence: str,
) -> TopSuspiciousEntity | None:
    top = _top_pairwise_bucket(feature)
    if not top:
        return None
    doc_count = max(int(top["doc_count"]), 1)
    unique_count = int(top["unique_count"])
    return TopSuspiciousEntity(
        entity_type=feature.entity_field,
        value=str(top["entity_value"]),
        count=unique_count,
        ratio=unique_count / doc_count,
        evidence=evidence,
    )


def _top_pairwise_bucket(
    feature: PairwiseCardinalityFeature | None,
) -> dict[str, str | int | float] | None:
    if not feature or not feature.buckets:
        return None
    return feature.buckets[0]


def _build_recommended_queries(
    features: InvestigationFeatures,
    field_mappings: dict[str, str],
    playbook: PlaybookConfig,
) -> list[RecommendedQuery]:
    substitutions = {
        "client_ip_field": field_mappings.get("client_ip", "ClientIP.keyword"),
        "path_field": field_mappings.get("path", "ClientRequestPath.keyword"),
        "asn_field": field_mappings.get("asn", "ClientASN"),
        "device_id_field": field_mappings.get("device_id", "RequestHeaders.device-uid.keyword"),
        "account_id_field": field_mappings.get("account_id", "RequestHeaders.account-id.keyword"),
        "client_hint_field": field_mappings.get("client_hint", "RequestHeaders.client-id.keyword"),
        "session_id_field": field_mappings.get("session_id", "RequestHeaders.session-id.keyword"),
        "edge_status_field": field_mappings.get("edge_status", "EdgeResponseStatus"),
        "origin_status_field": field_mappings.get("origin_status", "OriginResponseStatus"),
        "security_action_field": field_mappings.get("security_action", "SecurityAction.keyword"),
        "top_ip": features.top_ip_concentration.top_value if features.top_ip_concentration else "*",
        "top_path": features.path_concentration.top_value if features.path_concentration else "*",
        "top_asn": features.top_asn_concentration.top_value if features.top_asn_concentration else "*",
        "top_device_id": features.device_concentration.top_value if features.device_concentration else "*",
        "top_account_id": (
            str(features.unique_devices_per_account.buckets[0]["entity_value"])
            if features.unique_devices_per_account and features.unique_devices_per_account.buckets
            else "*"
        ),
        "top_client_hint": features.client_hint_concentration.top_value if features.client_hint_concentration else "*",
        "top_session_id": features.session_concentration.top_value if features.session_concentration else "*",
    }

    queries: list[RecommendedQuery] = []
    formatter = Formatter()
    for template in playbook.recommended_query_templates:
        field_names = [
            field_name
            for _, field_name, _, _ in formatter.parse(template)
            if field_name
        ]
        if any(substitutions.get(field_name) == "*" for field_name in field_names if field_name.startswith("top_")):
            continue
        rendered = template.format(**substitutions)
        queries.append(
            RecommendedQuery(
                description="Playbook follow-up query",
                kql=rendered,
            )
        )
    return queries[:5]


def _is_concentrated(feature: ConcentrationFeature | None, minimum_ratio: float) -> bool:
    return bool(feature and feature.ratio >= minimum_ratio and feature.top_value)


def _pick_best_hypothesis(scores: dict[str, float]) -> tuple[str, float]:
    best_hypothesis, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score < 0.35:
        return "unknown", 0.20
    return best_hypothesis, min(best_score, 0.99)
