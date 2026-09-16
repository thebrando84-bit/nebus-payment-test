from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.payments.router import get_payment_service
from app.payments.schemas import PaymentDetail, PaymentStatus


class FakePaymentService:
    def __init__(self) -> None:
        self.payment_id = uuid4()
        self.created_at = datetime(2026, 9, 15, 10, 0, tzinfo=UTC)
        self.create_calls = []

    async def create_payment(self, *, command):
        self.create_calls.append(command)
        return PaymentDetail(
            payment_id=self.payment_id,
            amount=Decimal("125.50"),
            currency="RUB",
            description="Demo payment",
            metadata={"order_id": "1"},
            status=PaymentStatus.pending,
            idempotency_key=command.idempotency_key,
            webhook_url="https://example.com/webhook",
            created_at=self.created_at,
            processed_at=None,
        )

    async def get_payment(self, *, payment_id: UUID):
        if payment_id != self.payment_id:
            return None
        return PaymentDetail(
            payment_id=self.payment_id,
            amount=Decimal("125.50"),
            currency="RUB",
            description="Demo payment",
            metadata={"order_id": "1"},
            status=PaymentStatus.pending,
            idempotency_key="idem-001",
            webhook_url="https://example.com/webhook",
            created_at=self.created_at,
            processed_at=None,
        )


@pytest.fixture
def payment_service(client):
    service = FakePaymentService()
    client.app.dependency_overrides[get_payment_service] = lambda: service
    yield service
    client.app.dependency_overrides.clear()


def test_create_payment_returns_accepted(client, api_key, payment_service):
    response = client.post(
        "/api/v1/payments",
        headers={"X-API-Key": api_key, "Idempotency-Key": "idem-001"},
        json={
            "amount": "125.50",
            "currency": "RUB",
            "description": "Demo payment",
            "metadata": {"order_id": "1"},
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "payment_id": str(payment_service.payment_id),
        "amount": "125.50",
        "currency": "RUB",
        "description": "Demo payment",
        "metadata": {"order_id": "1"},
        "status": "pending",
        "idempotency_key": "idem-001",
        "webhook_url": "https://example.com/webhook",
        "created_at": "2026-09-15T10:00:00Z",
        "processed_at": None,
    }
    assert payment_service.create_calls[0].idempotency_key == "idem-001"


def test_create_payment_requires_idempotency_key(client, api_key, payment_service):
    response = client.post(
        "/api/v1/payments",
        headers={"X-API-Key": api_key},
        json={
            "amount": "125.50",
            "currency": "RUB",
            "description": "Demo payment",
            "metadata": {},
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert response.status_code == 422
    assert payment_service.create_calls == []


def test_get_payment_returns_detail(client, api_key, payment_service):
    response = client.get(
        f"/api/v1/payments/{payment_service.payment_id}",
        headers={"X-API-Key": api_key},
    )

    assert response.status_code == 200
    assert response.json()["payment_id"] == str(payment_service.payment_id)
    assert response.json()["status"] == "pending"


def test_get_payment_returns_404_for_unknown_payment(client, api_key, payment_service):
    response = client.get(
        f"/api/v1/payments/{uuid4()}",
        headers={"X-API-Key": api_key},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Payment not found"}
