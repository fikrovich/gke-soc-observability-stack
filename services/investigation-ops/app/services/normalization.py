from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from app.core.settings import Settings
from app.models.grafana import GrafanaAlert, GrafanaWebhookPayload
from app.models.investigation import (
    AlertMetadata,
    EntityHints,
    InvestigationAccepted,
    InvestigationJob,
    InvestigationTimeWindow,
)
from app.models.playbook import PlaybookConfig
from app.playbooks.loader import PlaybookRegistry
from app.services.identifiers import build_incident_id, build_job_id

IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
ASN_PATTERN = re.compile(r"\bAS?(\d{1,10})\b", re.IGNORECASE)

ALERT_NAME_KEYS = ("alertname", "alert_name", "name")
ENVIRONMENT_KEYS = ("environment", "env", "namespace")
SERVICE_KEYS = ("service", "app", "application")
SEVERITY_KEYS = ("severity", "level")
DATASOURCE_KEYS = ("datasource", "data_source", "source")


def normalize_payload(
    payload: GrafanaWebhookPayload,
    *,
    raw_payload_hash: str,
    settings: Settings,
    playbooks: PlaybookRegistry,
    received_at: datetime | None = None,
) -> tuple[list[InvestigationJob], list[InvestigationAccepted]]:
    normalized_received_at = received_at or datetime.now(UTC)
    jobs: list[InvestigationJob] = []
    accepted: list[InvestigationAccepted] = []

    for alert in payload.alerts:
        metadata = build_alert_metadata(payload, alert)
        playbook = playbooks.match(metadata)
        time_window = build_time_window(
            alert,
            playbook,
            settings,
            reference_time=normalized_received_at,
        )
        entity_hints = extract_entity_hints(metadata)
        fingerprint = metadata.fingerprint
        incident_id = build_incident_id(
            fingerprint,
            metadata.alert_name,
            metadata.environment or "unknown",
            metadata.starts_at.isoformat(),
        )
        job_id = build_job_id(incident_id, normalized_received_at)
        job = InvestigationJob(
            job_id=job_id,
            incident_id=incident_id,
            received_at=normalized_received_at,
            alert=metadata,
            time_window=time_window,
            entity_hints=entity_hints,
            playbook_id=playbook.id,
            fingerprint=fingerprint,
            raw_payload_hash=raw_payload_hash,
        )
        jobs.append(job)
        accepted.append(
            InvestigationAccepted(
                incident_id=incident_id,
                job_id=job_id,
                playbook_id=playbook.id,
                fingerprint=fingerprint,
            )
        )

    return jobs, accepted


def build_alert_metadata(payload: GrafanaWebhookPayload, alert: GrafanaAlert) -> AlertMetadata:
    labels = dict(payload.common_labels)
    labels.update(alert.labels)

    annotations = dict(payload.common_annotations)
    annotations.update(alert.annotations)

    label_lookup = _casefold_mapping(labels)
    annotation_lookup = _casefold_mapping(annotations)

    alert_name = (
        _pick_first(label_lookup, ALERT_NAME_KEYS)
        or _pick_first(annotation_lookup, ALERT_NAME_KEYS)
        or "unknown-alert"
    )
    fingerprint = alert.fingerprint or build_incident_id(
        alert_name,
        alert.starts_at.isoformat(),
        str(labels),
    )

    values = {
        key: value
        for key, value in alert.values.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }

    return AlertMetadata(
        source_receiver=payload.receiver,
        status=alert.status,
        alert_name=alert_name,
        environment=_pick_first(label_lookup, ENVIRONMENT_KEYS) or _pick_first(annotation_lookup, ENVIRONMENT_KEYS),
        service=_pick_first(label_lookup, SERVICE_KEYS) or _pick_first(annotation_lookup, SERVICE_KEYS),
        severity=_pick_first(label_lookup, SEVERITY_KEYS) or _pick_first(annotation_lookup, SEVERITY_KEYS),
        datasource=_pick_first(label_lookup, DATASOURCE_KEYS) or _pick_first(annotation_lookup, DATASOURCE_KEYS),
        fingerprint=fingerprint,
        starts_at=alert.starts_at,
        ends_at=alert.ends_at,
        generator_url=alert.generator_url,
        dashboard_url=alert.dashboard_url,
        panel_url=alert.panel_url,
        labels=labels,
        annotations=annotations,
        values=values,
    )


def build_time_window(
    alert: GrafanaAlert,
    playbook: PlaybookConfig,
    settings: Settings,
    *,
    reference_time: datetime | None = None,
) -> InvestigationTimeWindow:
    lookback = playbook.window.lookback_minutes or settings.default_window_lookback_minutes
    baseline_windows = playbook.baseline.offset_windows or settings.default_baseline_windows
    baseline_window_minutes = playbook.baseline.window_minutes or lookback

    anchor = _window_anchor(alert, reference_time)
    start = anchor - timedelta(minutes=lookback)
    end = anchor
    if end <= start:
        end = start + timedelta(minutes=max(lookback, 1))

    baseline_end = start
    baseline_start = baseline_end - timedelta(
        minutes=baseline_window_minutes * baseline_windows
    )
    return InvestigationTimeWindow(
        start=start,
        end=end,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        baseline_windows=baseline_windows,
    )


def _window_anchor(alert: GrafanaAlert, reference_time: datetime | None) -> datetime:
    if alert.status == "resolved" and alert.ends_at:
        return alert.ends_at
    if reference_time:
        return reference_time
    if alert.ends_at:
        return alert.ends_at
    return alert.starts_at


def extract_entity_hints(metadata: AlertMetadata) -> EntityHints:
    ip_addresses: list[str] = []
    routes: list[str] = []
    account_ids: list[str] = []
    device_ids: list[str] = []
    asns: list[int] = []
    user_agents: list[str] = []
    client_ids: list[str] = []
    session_ids: list[str] = []

    combined = {
        **metadata.labels,
        **metadata.annotations,
        **{key: str(value) for key, value in metadata.values.items() if value is not None},
    }

    for key, raw_value in combined.items():
        lower_key = key.lower()
        values = _split_values(raw_value)

        for value in values:
            if "ip" in lower_key:
                ip_addresses.extend(_extract_ips(value))
            if "route" in lower_key or "path" in lower_key or "uri" in lower_key:
                route, parsed_entities = _extract_path_entities(value)
                if route:
                    routes.append(route)
                account_ids.extend(parsed_entities["account_ids"])
                device_ids.extend(parsed_entities["device_ids"])
                client_ids.extend(parsed_entities["client_ids"])
                session_ids.extend(parsed_entities["session_ids"])
            if _is_account_key(lower_key) and value:
                account_ids.append(value)
            if _is_device_id_key(lower_key) and value:
                device_ids.append(value)
            if _is_user_agent_key(lower_key):
                user_agents.append(value)
            if "asn" in lower_key:
                asns.extend(_extract_asns(value))
            if _is_client_id_key(lower_key):
                client_ids.append(value)
            if _is_session_id_key(lower_key):
                session_ids.append(value)

        ip_addresses.extend(_extract_ips(raw_value))
        asns.extend(_extract_asns(raw_value))

    return EntityHints(
        ip_addresses=_dedupe(ip_addresses),
        routes=_dedupe(routes),
        account_ids=_dedupe(account_ids),
        device_ids=_dedupe(device_ids),
        asns=[int(item) for item in _dedupe([str(asn) for asn in asns])],
        user_agents=_dedupe(user_agents),
        client_ids=_dedupe(client_ids),
        session_ids=_dedupe(session_ids),
    )


def _pick_first(mapping: dict[str, str], keys: Iterable[str]) -> str | None:
    for key in keys:
        lowered = key.lower()
        if mapping.get(lowered):
            return mapping[lowered]
    return None


def _split_values(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,;\n]", value) if item.strip()]


def _casefold_mapping(mapping: dict[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in mapping.items() if value not in (None, "")}


def _extract_ips(value: str) -> list[str]:
    results: list[str] = []
    for candidate in IP_PATTERN.findall(value):
        try:
            results.append(str(ipaddress.ip_address(candidate)))
        except ValueError:
            continue
    return results


def _extract_asns(value: str) -> list[int]:
    return [int(match.group(1)) for match in ASN_PATTERN.finditer(value)]


def _extract_path_entities(value: str) -> tuple[str | None, dict[str, list[str]]]:
    empty = {
        "account_ids": [],
        "device_ids": [],
        "client_ids": [],
        "session_ids": [],
    }
    if not value:
        return None, empty

    if value.startswith("/"):
        parsed = urlsplit(f"https://placeholder{value}")
    elif "://" in value:
        parsed = urlsplit(value)
    else:
        return None, empty

    if not parsed.path.startswith("/"):
        return None, empty

    for key, item in parse_qsl(parsed.query, keep_blank_values=False):
        lower_key = key.lower()
        if _is_account_key(lower_key):
            empty["account_ids"].append(item)
        if _is_device_id_key(lower_key):
            empty["device_ids"].append(item)
        if _is_client_id_key(lower_key):
            empty["client_ids"].append(item)
        if _is_session_id_key(lower_key):
            empty["session_ids"].append(item)

    return parsed.path, empty


def _is_account_key(value: str) -> bool:
    if "agent" in value:
        return False
    return value in {"account_id", "customer_id", "user_id", "account-id", "hs_user_id"} or (
        "account" in value and "id" in value
    ) or (
        "customer" in value and "id" in value
    ) or (
        "user" in value and "id" in value
    )


def _is_device_id_key(value: str) -> bool:
    return value in {"device_id", "device-uid"} or ("device" in value and ("id" in value or "uid" in value))


def _is_user_agent_key(value: str) -> bool:
    return "user_agent" in value or "user-agent" in value or "useragent" in value or value.endswith("ua")


def _is_client_id_key(value: str) -> bool:
    return "client" in value and "id" in value


def _is_session_id_key(value: str) -> bool:
    return "session" in value and "id" in value


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
