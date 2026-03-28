from __future__ import annotations

from base64 import b64encode
import json
from pathlib import Path

import pytest

from app.models.grafana import GrafanaWebhookPayload
from app.services.validation import validate_grafana_payload, validate_webhook_token

ROOT = Path(__file__).resolve().parents[2]


def test_validate_webhook_token() -> None:
    assert validate_webhook_token("shared-secret", "shared-secret") is True
    assert validate_webhook_token("wrong", "shared-secret") is False
    assert validate_webhook_token(None, "shared-secret") is False
    basic = "Basic " + b64encode(b"grafana:shared-secret").decode("utf-8")
    assert validate_webhook_token(None, "shared-secret", basic) is True
    bearer = "Bearer shared-secret"
    assert validate_webhook_token(None, "shared-secret", bearer) is True


def test_validate_grafana_payload_rejects_invalid_status() -> None:
    payload = json.loads((ROOT / "tests/fixtures/grafana_webhook_payload.json").read_text())
    payload["status"] = "paused"

    with pytest.raises(ValueError, match="unsupported Grafana payload status"):
        validate_grafana_payload(GrafanaWebhookPayload.model_validate(payload))


def test_validate_grafana_payload_rejects_reversed_timestamps() -> None:
    payload = json.loads((ROOT / "tests/fixtures/grafana_webhook_payload.json").read_text())
    payload["alerts"][0]["endsAt"] = "2026-03-14T09:00:00Z"

    with pytest.raises(ValueError, match="earlier than startsAt"):
        validate_grafana_payload(GrafanaWebhookPayload.model_validate(payload))


def test_validate_grafana_payload_accepts_grafana_zero_value_ends_at() -> None:
    payload = json.loads((ROOT / "tests/fixtures/grafana_webhook_payload.json").read_text())
    payload["alerts"][0]["endsAt"] = "0001-01-01T00:00:00Z"

    parsed = GrafanaWebhookPayload.model_validate(payload)

    assert parsed.alerts[0].ends_at is None
    validate_grafana_payload(parsed)
