from __future__ import annotations

from app.models.investigation import InvestigationResult


def build_slack_payload(result: InvestigationResult) -> dict:
    title = (
        f"[{result.alert_metadata.severity or 'unknown'}] "
        f"{result.alert_metadata.alert_name} "
        f"({result.preliminary_abuse_type_hypothesis}, confidence={result.confidence:.2f})"
    )
    evidence_lines = "\n".join(f"- {item}" for item in result.evidence_summary[:5]) or "- No evidence collected"
    suspicious_lines = "\n".join(
        f"- {entity.entity_type}: {entity.value} ({entity.count}, {entity.ratio:.2%})"
        for entity in result.top_suspicious_entities[:5]
    ) or "- No dominant entity"
    query_lines = "\n".join(
        f"- {item.description}: `{item.kql}`"
        for item in result.recommended_next_queries[:3]
    ) or "- No follow-up queries generated"

    return {
        "text": title,
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "Investigation Summary"}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Incident:* `{result.incident_id}`\n"
                        f"*Alert:* {result.alert_metadata.alert_name}\n"
                        f"*Hypothesis:* {result.preliminary_abuse_type_hypothesis}\n"
                        f"*Confidence:* {result.confidence:.2f}"
                    ),
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Evidence*\n{evidence_lines}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Suspicious entities*\n{suspicious_lines}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Next queries*\n{query_lines}"},
            },
        ],
    }

