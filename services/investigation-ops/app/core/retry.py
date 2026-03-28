from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar


T = TypeVar("T")


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    backoff_seconds: float,
) -> T:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == attempts:
                raise
            await asyncio.sleep(backoff_seconds * attempt)
    raise RuntimeError("retry_async exhausted without returning or raising") from last_error

