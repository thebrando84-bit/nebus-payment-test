import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from faststream import FastStream
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.messaging.broker import broker, declare_payment_topology, payments_new_queue
from app.payments.models import Payment
from app.payments.schemas import PaymentStatus
from app.webhooks.client import WebhookResult, send_webhook_with_retry


@dataclass(frozen=True, slots=True)
class ConsumerResult:
    payment_id: UUID
    status: PaymentStatus
    webhook: WebhookResult | object


async def emulate_payment_processing(
    *,
    random_value: float | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> PaymentStatus:
    await sleep(random.uniform(2, 5))
    value = random.random() if random_value is None else random_value
    return PaymentStatus.succeeded if value < 0.9 else PaymentStatus.failed


async def process_payment_message(
    message: dict[str, str],
    *,
    session: AsyncSession,
    webhook_sender=send_webhook_with_retry,
    random_value: float | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    webhook_attempts: int = 3,
    webhook_base_delay_seconds: float = 0.5,
) -> ConsumerResult:
    payment_id = UUID(message["payment_id"])
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise ValueError(f"Payment not found: {payment_id}")

    if payment.status == PaymentStatus.pending.value:
        status = await emulate_payment_processing(random_value=random_value, sleep=sleep)
        payment.status = status.value
        payment.processed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(payment)
    else:
        status = PaymentStatus(payment.status)

    webhook_result = await webhook_sender(
        url=payment.webhook_url,
        payload={"payment_id": str(payment.id), "status": payment.status},
        attempts=webhook_attempts,
        base_delay_seconds=webhook_base_delay_seconds,
    )
    if getattr(webhook_result, "delivered", True) is False:
        raise RuntimeError(f"Webhook delivery failed for payment {payment.id}")
    return ConsumerResult(payment_id=payment.id, status=status, webhook=webhook_result)


@broker.subscriber(payments_new_queue)
async def handle_payment_created(message: dict[str, str]) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        await process_payment_message(
            message,
            session=session,
            webhook_attempts=settings.webhook_attempts,
            webhook_base_delay_seconds=settings.webhook_base_delay_seconds,
        )


app = FastStream(broker)


@app.after_startup
async def setup_payment_topology() -> None:
    await declare_payment_topology(broker)



