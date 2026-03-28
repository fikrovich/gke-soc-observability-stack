from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GrafanaAlert(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    status: str
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    generator_url: str | None = Field(default=None, alias="generatorURL")
    fingerprint: str | None = None
    silence_url: str | None = Field(default=None, alias="silenceURL")
    dashboard_url: str | None = Field(default=None, alias="dashboardURL")
    panel_url: str | None = Field(default=None, alias="panelURL")
    values: dict[str, Any] = Field(default_factory=dict)
    value_string: str | None = Field(default=None, alias="valueString")

    @model_validator(mode="after")
    def normalize_empty_ends_at(self) -> "GrafanaAlert":
        # Grafana sends year 1 as a zero-value endsAt for firing test alerts.
        if self.ends_at and self.ends_at.year <= 1:
            self.ends_at = None
        return self


class GrafanaWebhookPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    receiver: str | None = None
    status: str
    org_id: int | None = Field(default=None, alias="orgId")
    alerts: list[GrafanaAlert]
    group_labels: dict[str, str] = Field(default_factory=dict, alias="groupLabels")
    common_labels: dict[str, str] = Field(default_factory=dict, alias="commonLabels")
    common_annotations: dict[str, str] = Field(default_factory=dict, alias="commonAnnotations")
    external_url: str | None = Field(default=None, alias="externalURL")
    version: str | None = None
    group_key: str | None = Field(default=None, alias="groupKey")
    truncated_alerts: int = Field(default=0, alias="truncatedAlerts")
