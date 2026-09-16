from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.consumer.payment_consumer import process_payment_message
from app.db.base import Base
from app.payments.models import Payment
from app.payments.schemas import PaymentStatus


class FakeWebhookResult:
    def __init__(self, delivered: bool = True) -> None:
        self.delivered = delivered


class FakeWebhookSender:
    def __init__(self, *, delivered: bool = True) -> None:
        self.delivered = delivered
        self.calls: list[dict[str, object]] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return FakeWebhookResult(delivered=self.delivered)


async def no_sleep(delay: float) -> None:
    return None


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def create_pending_payment(session, *, webhook_url: str = "https://example.com/webhook") -> Payment:
    payment = Payment(
        id=uuid4(),
        amount=Decimal("125.50"),
        currency="RUB",
        description="Demo payment",
        metadata_={"order_id": "1"},
        status=PaymentStatus.pending.value,
        idempotency_key="idem-001",
        webhook_url=webhook_url,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


@pytest.mark.asyncio
async def test_process_payment_message_marks_payment_succeeded_and_sends_webhook(session):
    payment = await create_pending_payment(session)
    webhook_sender = FakeWebhookSender()

    result = await process_payment_message(
        {"payment_id": str(payment.id)},
        session=session,
        webhook_sender=webhook_sender,
        random_value=0.1,
        sleep=no_sleep,
        webhook_attempts=3,
        webhook_base_delay_seconds=0,
    )

    await session.refresh(payment)
    assert result.status == PaymentStatus.succeeded
    assert payment.status == PaymentStatus.succeeded.value
    assert payment.processed_at is not None
    assert webhook_sender.calls[0]["url"] == "https://example.com/webhook"
    assert webhook_sender.calls[0]["payload"] == {
        "payment_id": str(payment.id),
        "status": "succeeded",
    }


@pytest.mark.asyncio
async def test_process_payment_message_marks_payment_failed_for_failed_emulation(session):
    payment = await create_pending_payment(session)
    webhook_sender = FakeWebhookSender()

    result = await process_payment_message(
        {"payment_id": str(payment.id)},
        session=session,
        webhook_sender=webhook_sender,
        random_value=0.95,
        sleep=no_sleep,
        webhook_attempts=3,
        webhook_base_delay_seconds=0,
    )

    await session.refresh(payment)
    assert result.status == PaymentStatus.failed
    assert payment.status == PaymentStatus.failed.value
    assert webhook_sender.calls[0]["payload"]["status"] == "failed"


@pytest.mark.asyncio
async def test_process_payment_message_raises_for_unknown_payment(session):
    with pytest.raises(ValueError, match="Payment not found"):
        await process_payment_message(
            {"payment_id": str(uuid4())},
            session=session,
            webhook_sender=FakeWebhookSender(),
            random_value=0.1,
            sleep=no_sleep,
            webhook_attempts=3,
            webhook_base_delay_seconds=0,
        )

@pytest.mark.asyncio
async def test_process_payment_message_preserves_terminal_status_on_duplicate_delivery(session):
    payment = await create_pending_payment(session)
    payment.status = PaymentStatus.succeeded.value
    await session.commit()
    webhook_sender = FakeWebhookSender()

    result = await process_payment_message(
        {"payment_id": str(payment.id)},
        session=session,
        webhook_sender=webhook_sender,
        random_value=0.95,
        sleep=no_sleep,
        webhook_attempts=3,
        webhook_base_delay_seconds=0,
    )

    await session.refresh(payment)
    assert result.status == PaymentStatus.succeeded
    assert payment.status == PaymentStatus.succeeded.value
    assert webhook_sender.calls[0]["payload"]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_process_payment_message_raises_when_webhook_is_not_delivered(session):
    payment = await create_pending_payment(session)

    with pytest.raises(RuntimeError, match="Webhook delivery failed"):
        await process_payment_message(
            {"payment_id": str(payment.id)},
            session=session,
            webhook_sender=FakeWebhookSender(delivered=False),
            random_value=0.1,
            sleep=no_sleep,
            webhook_attempts=3,
            webhook_base_delay_seconds=0,
        )

    await session.refresh(payment)
    assert payment.status == PaymentStatus.succeeded.value
