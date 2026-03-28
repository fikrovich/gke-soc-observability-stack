from __future__ import annotations

import secrets
from base64 import b64decode

from app.models.grafana import GrafanaWebhookPayload

VALID_ALERT_STATUSES = {"firing", "resolved"}


def validate_webhook_token(
    provided: str | None,
    expected: str,
    authorization: str | None = None,
) -> bool:
    if expected and provided and secrets.compare_digest(provided, expected):
        return True
    if not expected or not authorization:
        return False
    scheme, _, credentials = authorization.partition(" ")
    if not credentials:
        return False
    if scheme.lower() == "bearer":
        return secrets.compare_digest(credentials, expected)
    if scheme.lower() != "basic":
        return False
    try:
        decoded = b64decode(credentials).decode("utf-8")
    except Exception:  # noqa: BLE001
        return False
    _, _, password = decoded.partition(":")
    if not password:
        return False
    return secrets.compare_digest(password, expected)


def validate_grafana_payload(payload: GrafanaWebhookPayload) -> None:
    if not payload.alerts:
        raise ValueError("Grafana payload contained no alerts")
    if payload.status not in VALID_ALERT_STATUSES:
        raise ValueError(f"unsupported Grafana payload status: {payload.status}")
    for alert in payload.alerts:
        if alert.status not in VALID_ALERT_STATUSES:
            raise ValueError(f"unsupported alert status: {alert.status}")
        if alert.ends_at and alert.ends_at < alert.starts_at:
            raise ValueError("alert endsAt is earlier than startsAt")
