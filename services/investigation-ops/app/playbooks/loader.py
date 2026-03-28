from __future__ import annotations

from pathlib import Path

import yaml

from app.models.investigation import AlertMetadata
from app.models.playbook import PlaybookConfig


class PlaybookRegistry:
    def __init__(self, playbooks: list[PlaybookConfig]) -> None:
        if not playbooks:
            raise ValueError("at least one playbook is required")
        defaults = [playbook for playbook in playbooks if playbook.default]
        if len(defaults) > 1:
            raise ValueError("only one default playbook is allowed")
        self._playbooks = playbooks

    @property
    def playbooks(self) -> list[PlaybookConfig]:
        return list(self._playbooks)

    def default(self) -> PlaybookConfig:
        for playbook in self._playbooks:
            if playbook.default:
                return playbook
        return self._playbooks[0]

    def get(self, playbook_id: str) -> PlaybookConfig:
        for playbook in self._playbooks:
            if playbook.id == playbook_id:
                return playbook
        raise KeyError(f"unknown playbook: {playbook_id}")

    def match(self, alert: AlertMetadata) -> PlaybookConfig:
        for playbook in self._playbooks:
            if playbook.default:
                continue
            if self._matches(playbook, alert):
                return playbook
        return self.default()

    def _matches(self, playbook: PlaybookConfig, alert: AlertMetadata) -> bool:
        match = playbook.match
        haystack_name = (alert.alert_name or "").lower()
        if match.alert_name_contains and not any(
            needle.lower() in haystack_name for needle in match.alert_name_contains
        ):
            return False

        service = (alert.service or "").lower()
        if match.service_in and service not in {item.lower() for item in match.service_in}:
            return False

        for key, values in match.label_equals.items():
            if alert.labels.get(key) not in values:
                return False

        for key, needles in match.annotation_contains.items():
            value = (alert.annotations.get(key) or "").lower()
            if not any(needle.lower() in value for needle in needles):
                return False

        return True


def load_playbooks(
    playbook_dir: Path,
    *,
    field_mapping_overrides_path: Path | None = None,
) -> PlaybookRegistry:
    files = sorted(playbook_dir.glob("*.yaml"))
    overrides: dict[str, str] = {}
    if field_mapping_overrides_path and field_mapping_overrides_path.exists():
        with field_mapping_overrides_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        overrides = {str(key): str(value) for key, value in loaded.items() if value}
    playbooks = []
    for file_path in files:
        with file_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
        payload["field_mappings"] = {
            **payload.get("field_mappings", {}),
            **overrides,
        }
        playbooks.append(PlaybookConfig.model_validate(payload))
    return PlaybookRegistry(playbooks)
