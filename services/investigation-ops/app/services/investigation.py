from __future__ import annotations

from datetime import UTC, datetime

from app.core.retry import retry_async
from app.core.settings import Settings
from app.feature_extraction.extractor import extract_features
from app.integrations.elastic.client import ElasticsearchInvestigationClient
from app.integrations.elastic.query_builder import build_query_pack
from app.integrations.slack.client import SlackWebhookClient
from app.integrations.slack.formatter import build_slack_payload
from app.models.investigation import (
    InvestigationJob,
    InvestigationResult,
    NotificationStatus,
    ProcessingStatus,
)
from app.playbooks.loader import PlaybookRegistry
from app.scoring.hypothesis import score_investigation


class InvestigationProcessor:
    def __init__(
        self,
        *,
        settings: Settings,
        playbooks: PlaybookRegistry,
        elastic: ElasticsearchInvestigationClient,
        slack: SlackWebhookClient,
    ) -> None:
        self._settings = settings
        self._playbooks = playbooks
        self._elastic = elastic
        self._slack = slack

    async def process_job(self, job: InvestigationJob) -> InvestigationResult:
        processed_at = datetime.now(UTC)
        playbook = self._playbooks.get(job.playbook_id)
        try:
            query_pack = build_query_pack(
                job,
                playbook,
                max_terms_bucket_size=self._settings.max_terms_bucket_size,
            )
            alert_response, baseline_response = await retry_async(
                lambda: self._elastic.execute_queries(
                    self._settings.elasticsearch_index_alias,
                    query_pack.alert_query,
                    query_pack.baseline_query,
                ),
                attempts=self._settings.retry_attempts,
                backoff_seconds=self._settings.retry_backoff_seconds,
            )
            features = extract_features(
                playbook=playbook,
                query_pack=query_pack,
                alert_response=alert_response,
                baseline_response=baseline_response,
            )
            scoring = score_investigation(
                playbook=playbook,
                features=features,
                field_mappings=query_pack.field_mappings,
            )

            result = InvestigationResult(
                incident_id=job.incident_id,
                job_id=job.job_id,
                source_index_alias=self._settings.elasticsearch_index_alias,
                alert_metadata=job.alert,
                time_window=job.time_window,
                playbook_id=playbook.id,
                extracted_features=features,
                top_suspicious_entities=scoring.top_suspicious_entities,
                evidence_summary=scoring.evidence_summary,
                preliminary_abuse_type_hypothesis=scoring.hypothesis,
                confidence=scoring.confidence,
                recommended_next_queries=scoring.recommended_next_queries,
                recommended_mitigations=scoring.recommended_mitigations,
                notification_status=NotificationStatus.pending,
                processing_status=ProcessingStatus.completed,
                processed_at=processed_at,
            )
            await self._elastic.persist_result(result)

            if self._slack.configured:
                try:
                    await retry_async(
                        lambda: self._slack.send(build_slack_payload(result)),
                        attempts=self._settings.retry_attempts,
                        backoff_seconds=self._settings.retry_backoff_seconds,
                    )
                    result.notification_status = NotificationStatus.sent
                except Exception as exc:  # noqa: BLE001
                    result.notification_status = NotificationStatus.failed
                    result.error = str(exc)
                await self._elastic.persist_result(result)
            else:
                result.notification_status = NotificationStatus.skipped
                await self._elastic.persist_result(result)

            return result
        except Exception as exc:  # noqa: BLE001
            failed_result = InvestigationResult(
                incident_id=job.incident_id,
                job_id=job.job_id,
                source_index_alias=self._settings.elasticsearch_index_alias,
                alert_metadata=job.alert,
                time_window=job.time_window,
                playbook_id=job.playbook_id,
                evidence_summary=["Investigation processing failed before feature extraction completed."],
                preliminary_abuse_type_hypothesis="unknown",
                confidence=0.0,
                notification_status=NotificationStatus.skipped,
                processing_status=ProcessingStatus.failed,
                error=str(exc),
                processed_at=processed_at,
            )
            await self._elastic.persist_result(failed_result)
            return failed_result

