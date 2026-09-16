from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.payments.schemas import CreatePaymentCommand, PaymentStatus
from app.payments.service import PaymentRecord, PaymentService


class FakePaymentRepository:
    def __init__(self) -> None:
        self.by_idempotency_key: dict[str, PaymentRecord] = {}
        self.by_id: dict[UUID, PaymentRecord] = {}
        self.outbox_events: list[dict[str, object]] = []

    async def get_by_idempotency_key(self, idempotency_key: str) -> PaymentRecord | None:
        return self.by_idempotency_key.get(idempotency_key)

    async def get_by_id(self, payment_id: UUID) -> PaymentRecord | None:
        return self.by_id.get(payment_id)

    async def create_payment_with_outbox(self, command: CreatePaymentCommand) -> PaymentRecord:
        record = PaymentRecord(
            payment_id=uuid4(),
            amount=command.amount,
            currency=command.currency,
            description=command.description,
            metadata=command.metadata,
            status=PaymentStatus.pending,
            idempotency_key=command.idempotency_key,
            webhook_url=command.webhook_url,
            created_at=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
            processed_at=None,
        )
        self.by_idempotency_key[record.idempotency_key] = record
        self.by_id[record.payment_id] = record
        self.outbox_events.append(
            {"event_type": "payment.created", "payload": {"payment_id": str(record.payment_id)}}
        )
        return record


def payment_command(idempotency_key: str = "idem-001") -> CreatePaymentCommand:
    return CreatePaymentCommand(
        amount=Decimal("125.50"),
        currency="RUB",
        description="Demo payment",
        metadata={"order_id": "1"},
        webhook_url="https://example.com/webhook",
        idempotency_key=idempotency_key,
    )


@pytest.mark.asyncio
async def test_create_payment_creates_pending_payment_and_outbox_event():
    repository = FakePaymentRepository()
    service = PaymentService(repository=repository)

    payment = await service.create_payment(command=payment_command())

    assert payment.status == PaymentStatus.pending
    assert payment.idempotency_key == "idem-001"
    assert repository.outbox_events == [
        {"event_type": "payment.created", "payload": {"payment_id": str(payment.payment_id)}}
    ]


@pytest.mark.asyncio
async def test_create_payment_is_idempotent_by_key():
    repository = FakePaymentRepository()
    service = PaymentService(repository=repository)

    first = await service.create_payment(command=payment_command("same-key"))
    second = await service.create_payment(command=payment_command("same-key"))

    assert first == second
    assert len(repository.outbox_events) == 1


@pytest.mark.asyncio
async def test_get_payment_returns_none_for_unknown_id():
    repository = FakePaymentRepository()
    service = PaymentService(repository=repository)

    payment = await service.get_payment(payment_id=uuid4())

    assert payment is None
