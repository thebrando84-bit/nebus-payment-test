from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.payments.schemas import CreatePaymentCommand, PaymentDetail, PaymentStatus


@dataclass(frozen=True, slots=True)
class PaymentRecord:
    payment_id: UUID
    amount: Decimal
    currency: str
    description: str
    metadata: dict[str, object]
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None


class PaymentRepository(Protocol):
    async def get_by_idempotency_key(self, idempotency_key: str) -> PaymentRecord | None: ...

    async def get_by_id(self, payment_id: UUID) -> PaymentRecord | None: ...

    async def create_payment_with_outbox(self, command: CreatePaymentCommand) -> PaymentRecord: ...


class PaymentService:
    def __init__(self, repository: PaymentRepository) -> None:
        self._repository = repository

    async def create_payment(self, *, command: CreatePaymentCommand) -> PaymentDetail:
        existing = await self._repository.get_by_idempotency_key(command.idempotency_key)
        if existing is not None:
            return self._to_detail(existing)

        payment = await self._repository.create_payment_with_outbox(command)
        return self._to_detail(payment)

    async def get_payment(self, *, payment_id: UUID) -> PaymentDetail | None:
        payment = await self._repository.get_by_id(payment_id)
        if payment is None:
            return None
        return self._to_detail(payment)

    @staticmethod
    def _to_detail(payment: PaymentRecord) -> PaymentDetail:
        return PaymentDetail(
            payment_id=payment.payment_id,
            amount=payment.amount,
            currency=payment.currency,
            description=payment.description,
            metadata=payment.metadata,
            status=payment.status,
            idempotency_key=payment.idempotency_key,
            webhook_url=payment.webhook_url,
            created_at=payment.created_at,
            processed_at=payment.processed_at,
        )
