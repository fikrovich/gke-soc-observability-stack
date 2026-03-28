from __future__ import annotations

import httpx

from app.core.settings import Settings


class SlackWebhookClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client:
            return
        self._client = httpx.AsyncClient(timeout=self._settings.slack_timeout_seconds)

    async def stop(self) -> None:
        if not self._client:
            return
        await self._client.aclose()
        self._client = None

    async def send(self, payload: dict) -> None:
        if not self._settings.slack_webhook_url:
            raise RuntimeError("SLACK_WEBHOOK_URL is not configured")
        if not self._client:
            raise RuntimeError("Slack client is not started")
        response = await self._client.post(self._settings.slack_webhook_url, json=payload)
        response.raise_for_status()

    @property
    def configured(self) -> bool:
        return bool(self._settings.slack_webhook_url)

