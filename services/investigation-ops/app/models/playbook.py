from __future__ import annotations

from pydantic import BaseModel, Field


class PlaybookMatch(BaseModel):
    alert_name_contains: list[str] = Field(default_factory=list)
    service_in: list[str] = Field(default_factory=list)
    label_equals: dict[str, list[str]] = Field(default_factory=dict)
    annotation_contains: dict[str, list[str]] = Field(default_factory=dict)


class PlaybookFilter(BaseModel):
    canonical_field: str
    operator: str
    value: str | int | float | bool | None = None
    values: list[str | int | float | bool] = Field(default_factory=list)
    required: bool = False


class PlaybookWindow(BaseModel):
    lookback_minutes: int
    lookahead_minutes: int


class BaselineWindow(BaseModel):
    window_minutes: int
    offset_windows: int


class FeatureFlags(BaseModel):
    device_concentration: bool = True
    client_hint_concentration: bool = True
    session_concentration: bool = True
    unique_accounts_per_ip: bool = False
    unique_devices_per_account: bool = False
    unique_devices_per_ip: bool = False
    unique_ips_per_device: bool = False
    unique_ips_per_session: bool = False
    new_account_ratio: bool = False
    challenge_outcome_distribution: bool = False


class HypothesisThresholds(BaseModel):
    concentration_ratio_high: float = 0.65
    request_spike_ratio_high: float = 3.0
    request_spike_delta_high: float = 500.0
    suspicious_action_ratio: float = 0.3


class PlaybookConfig(BaseModel):
    id: str
    description: str
    default: bool = False
    analysis_mode: str = "generic"
    match: PlaybookMatch
    window: PlaybookWindow
    baseline: BaselineWindow
    indices: list[str] = Field(default_factory=list)
    filters: list[PlaybookFilter] = Field(default_factory=list)
    field_mappings: dict[str, str] = Field(default_factory=dict)
    feature_flags: FeatureFlags = Field(default_factory=FeatureFlags)
    hypothesis_thresholds: HypothesisThresholds = Field(default_factory=HypothesisThresholds)
    recommended_mitigations: list[str] = Field(default_factory=list)
    recommended_query_templates: list[str] = Field(default_factory=list)
