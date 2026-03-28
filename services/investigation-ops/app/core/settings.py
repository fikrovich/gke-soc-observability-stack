from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    service_name: str = Field(default="investigation-ops", alias="SERVICE_NAME")
    environment: str = Field(default="production", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8080, alias="API_PORT")
    worker_host: str = Field(default="0.0.0.0", alias="WORKER_HOST")
    worker_port: int = Field(default=8080, alias="WORKER_PORT")

    webhook_shared_token: str = Field(default="", alias="WEBHOOK_SHARED_TOKEN")

    kafka_bootstrap_servers: list[str] = Field(
        default_factory=lambda: ["localhost:9092"],
        alias="KAFKA_BOOTSTRAP_SERVERS",
    )
    investigation_job_topic: str = Field(
        default="investigations",
        alias="INVESTIGATION_JOB_TOPIC",
    )
    investigation_consumer_group: str = Field(
        default="investigation-ops-worker",
        alias="INVESTIGATION_CONSUMER_GROUP",
    )
    kafka_client_id: str = Field(default="investigation-ops", alias="KAFKA_CLIENT_ID")
    kafka_request_timeout_ms: int = Field(default=30000, alias="KAFKA_REQUEST_TIMEOUT_MS")

    elasticsearch_url: str = Field(
        default="https://search-stack-es-http.observability:9200",
        alias="ELASTICSEARCH_URL",
    )
    elasticsearch_username: str = Field(default="", alias="ELASTICSEARCH_USERNAME")
    elasticsearch_password: str = Field(default="", alias="ELASTICSEARCH_PASSWORD")
    elasticsearch_ca_cert_path: str = Field(
        default="/var/run/secrets/elastic/tls.crt",
        alias="ELASTICSEARCH_CA_CERT_PATH",
    )
    elasticsearch_index_alias: str = Field(
        default="edge-logs",
        alias="ELASTICSEARCH_INDEX_ALIAS",
    )
    result_index: str = Field(
        default="investigation-results-v1",
        alias="RESULT_INDEX",
    )
    elasticsearch_request_timeout_seconds: int = Field(
        default=30,
        alias="ELASTICSEARCH_REQUEST_TIMEOUT_SECONDS",
    )

    slack_webhook_url: str = Field(default="", alias="SLACK_WEBHOOK_URL")
    slack_timeout_seconds: int = Field(default=10, alias="SLACK_TIMEOUT_SECONDS")

    playbook_dir: Path = Field(default=Path("config/playbooks"), alias="PLAYBOOK_DIR")
    field_mapping_overrides_path: Path | None = Field(
        default=None,
        alias="FIELD_MAPPING_OVERRIDES_PATH",
    )

    default_window_lookback_minutes: int = Field(
        default=15,
        alias="DEFAULT_WINDOW_LOOKBACK_MINUTES",
    )
    default_window_lookahead_minutes: int = Field(
        default=15,
        alias="DEFAULT_WINDOW_LOOKAHEAD_MINUTES",
    )
    default_baseline_windows: int = Field(default=6, alias="DEFAULT_BASELINE_WINDOWS")
    max_terms_bucket_size: int = Field(default=10, alias="MAX_TERMS_BUCKET_SIZE")

    retry_attempts: int = Field(default=3, alias="RETRY_ATTEMPTS")
    retry_backoff_seconds: float = Field(default=1.0, alias="RETRY_BACKOFF_SECONDS")

    @field_validator("kafka_bootstrap_servers", mode="before")
    @classmethod
    def split_bootstrap_servers(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        raise ValueError("KAFKA_BOOTSTRAP_SERVERS must be a comma-separated string or list")

    @field_validator("playbook_dir", "field_mapping_overrides_path", mode="before")
    @classmethod
    def coerce_paths(cls, value: object) -> Path | None:
        if value in (None, ""):
            return None
        return Path(str(value))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

