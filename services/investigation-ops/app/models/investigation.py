from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class NotificationStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


class ProcessingStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class EntityHints(BaseModel):
    ip_addresses: list[str] = Field(default_factory=list)
    routes: list[str] = Field(default_factory=list)
    account_ids: list[str] = Field(default_factory=list)
    device_ids: list[str] = Field(default_factory=list)
    asns: list[int] = Field(default_factory=list)
    user_agents: list[str] = Field(default_factory=list)
    client_ids: list[str] = Field(default_factory=list)
    session_ids: list[str] = Field(default_factory=list)


class AlertMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "grafana"
    source_receiver: str | None = None
    status: str
    alert_name: str
    environment: str | None = None
    service: str | None = None
    severity: str | None = None
    datasource: str | None = None
    fingerprint: str
    starts_at: datetime
    ends_at: datetime | None = None
    generator_url: str | None = None
    dashboard_url: str | None = None
    panel_url: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    values: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class InvestigationTimeWindow(BaseModel):
    start: datetime
    end: datetime
    baseline_start: datetime
    baseline_end: datetime
    baseline_windows: int


class InvestigationJob(BaseModel):
    schema_version: str = "v1"
    job_id: str
    incident_id: str
    received_at: datetime
    source: str = "grafana"
    alert: AlertMetadata
    time_window: InvestigationTimeWindow
    entity_hints: EntityHints = Field(default_factory=EntityHints)
    playbook_id: str
    fingerprint: str
    raw_payload_hash: str


class InvestigationAccepted(BaseModel):
    incident_id: str
    job_id: str
    playbook_id: str
    fingerprint: str


class DistributionBucket(BaseModel):
    key: str
    count: int
    ratio: float


class VolumeDeltaFeature(BaseModel):
    current_count: int
    baseline_average: float
    delta: float
    ratio: float | None = None


class ConcentrationFeature(BaseModel):
    field: str
    top_value: str | None = None
    top_count: int = 0
    ratio: float = 0.0
    buckets: list[DistributionBucket] = Field(default_factory=list)


class PairwiseCardinalityFeature(BaseModel):
    entity_field: str
    cardinality_field: str
    buckets: list[dict[str, str | int | float]] = Field(default_factory=list)


class InvestigationFeatures(BaseModel):
    request_count_delta: VolumeDeltaFeature
    top_ip_concentration: ConcentrationFeature | None = None
    top_asn_concentration: ConcentrationFeature | None = None
    top_user_agent_concentration: ConcentrationFeature | None = None
    response_status_distribution: list[DistributionBucket] = Field(default_factory=list)
    challenge_outcome_distribution: list[DistributionBucket] = Field(default_factory=list)
    security_action_concentration: ConcentrationFeature | None = None
    security_rule_concentration: ConcentrationFeature | None = None
    path_concentration: ConcentrationFeature | None = None
    device_concentration: ConcentrationFeature | None = None
    client_hint_concentration: ConcentrationFeature | None = None
    session_concentration: ConcentrationFeature | None = None
    unique_accounts_per_ip: PairwiseCardinalityFeature | None = None
    unique_devices_per_account: PairwiseCardinalityFeature | None = None
    unique_devices_per_ip: PairwiseCardinalityFeature | None = None
    unique_ips_per_device: PairwiseCardinalityFeature | None = None
    unique_ips_per_session: PairwiseCardinalityFeature | None = None
    new_account_ratio: float | None = None
    unavailable_features: list[str] = Field(default_factory=list)


class TopSuspiciousEntity(BaseModel):
    entity_type: str
    value: str
    count: int
    ratio: float
    evidence: str


class RecommendedQuery(BaseModel):
    description: str
    kql: str


class InvestigationResult(BaseModel):
    schema_version: str = "v1"
    incident_id: str
    job_id: str
    source_index_alias: str
    alert_metadata: AlertMetadata
    time_window: InvestigationTimeWindow
    playbook_id: str
    extracted_features: InvestigationFeatures | None = None
    top_suspicious_entities: list[TopSuspiciousEntity] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    preliminary_abuse_type_hypothesis: str = "unknown"
    confidence: float = 0.0
    recommended_next_queries: list[RecommendedQuery] = Field(default_factory=list)
    recommended_mitigations: list[str] = Field(default_factory=list)
    notification_status: NotificationStatus = NotificationStatus.pending
    processing_status: ProcessingStatus = ProcessingStatus.pending
    error: str | None = None
    processed_at: datetime
