from datetime import UTC
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.models import OutboxEvent, Payment
from app.payments.schemas import CreatePaymentCommand, PaymentStatus
from app.payments.service import PaymentRecord


class SqlAlchemyPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_idempotency_key(self, idempotency_key: str) -> PaymentRecord | None:
        result = await self._session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            return None
        return self._to_record(payment)

    async def get_by_id(self, payment_id: UUID) -> PaymentRecord | None:
        payment = await self._session.get(Payment, payment_id)
        if payment is None:
            return None
        return self._to_record(payment)

    async def create_payment_with_outbox(self, command: CreatePaymentCommand) -> PaymentRecord:
        payment_id = uuid4()
        payment = Payment(
            id=payment_id,
            amount=command.amount,
            currency=command.currency,
            description=command.description,
            metadata_=command.metadata,
            status=PaymentStatus.pending.value,
            idempotency_key=command.idempotency_key,
            webhook_url=command.webhook_url,
        )
        outbox_event = OutboxEvent(
            event_type="payment.created",
            payload={"payment_id": str(payment_id)},
        )
        self._session.add_all([payment, outbox_event])
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self.get_by_idempotency_key(command.idempotency_key)
            if existing is None:
                raise
            return existing

        await self._session.refresh(payment)
        return self._to_record(payment)

    @staticmethod
    def _to_record(payment: Payment) -> PaymentRecord:
        created_at = payment.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)

        processed_at = payment.processed_at
        if processed_at is not None and processed_at.tzinfo is None:
            processed_at = processed_at.replace(tzinfo=UTC)

        return PaymentRecord(
            payment_id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            description=payment.description,
            metadata=payment.metadata_,
            status=PaymentStatus(payment.status),
            idempotency_key=payment.idempotency_key,
            webhook_url=payment.webhook_url,
            created_at=created_at,
            processed_at=processed_at,
        )
