import httpx
import pytest

from app.webhooks.client import send_webhook_with_retry


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeHttpClient:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[tuple[str, dict[str, object], float]] = []

    async def post(self, url: str, json: dict[str, object], timeout: float):
        self.requests.append((url, json, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


async def no_sleep(delay: float) -> None:
    return None


@pytest.mark.asyncio
async def test_send_webhook_retries_until_success():
    client = FakeHttpClient([500, httpx.ConnectError("network"), 200])

    result = await send_webhook_with_retry(
        url="https://client.test/webhook",
        payload={"payment_id": "payment-1", "status": "succeeded"},
        attempts=3,
        base_delay_seconds=0,
        client=client,
        sleep=no_sleep,
    )

    assert result.delivered is True
    assert result.attempts == 3
    assert len(client.requests) == 3


@pytest.mark.asyncio
async def test_send_webhook_stops_after_max_attempts():
    client = FakeHttpClient([500, 503, 500])

    result = await send_webhook_with_retry(
        url="https://client.test/webhook",
        payload={"payment_id": "payment-1", "status": "failed"},
        attempts=3,
        base_delay_seconds=0,
        client=client,
        sleep=no_sleep,
    )

    assert result.delivered is False
    assert result.attempts == 3
    assert len(client.requests) == 3


@pytest.mark.asyncio
async def test_send_webhook_does_not_retry_success():
    client = FakeHttpClient([204])

    result = await send_webhook_with_retry(
        url="https://client.test/webhook",
        payload={"payment_id": "payment-1", "status": "succeeded"},
        attempts=3,
        base_delay_seconds=0,
        client=client,
        sleep=no_sleep,
    )

    assert result.delivered is True
    assert result.attempts == 1
    assert len(client.requests) == 1
