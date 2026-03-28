from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


def stable_hash(payload: dict[str, Any] | list[Any] | str) -> str:
    if isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def payload_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def build_incident_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def build_job_id(incident_id: str, received_at: datetime) -> str:
    return hashlib.sha256(
        f"{incident_id}|{received_at.isoformat()}".encode("utf-8")
    ).hexdigest()[:24]

