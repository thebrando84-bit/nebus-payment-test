import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import httpx


class AsyncHttpClient(Protocol):
    async def post(self, url: str, json: dict[str, object], timeout: float): ...


@dataclass(frozen=True, slots=True)
class WebhookResult:
    delivered: bool
    attempts: int


async def send_webhook_with_retry(
    *,
    url: str,
    payload: dict[str, object],
    attempts: int,
    base_delay_seconds: float,
    client: AsyncHttpClient | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> WebhookResult:
    owns_client = client is None
    http_client = client or httpx.AsyncClient()

    try:
        for attempt in range(1, attempts + 1):
            try:
                response = await http_client.post(url, json=payload, timeout=5.0)
                if 200 <= response.status_code < 300:
                    return WebhookResult(delivered=True, attempts=attempt)
            except httpx.HTTPError:
                pass

            if attempt < attempts:
                await sleep(base_delay_seconds * (2 ** (attempt - 1)))

        return WebhookResult(delivered=False, attempts=attempts)
    finally:
        if owns_client:
            await http_client.aclose()
