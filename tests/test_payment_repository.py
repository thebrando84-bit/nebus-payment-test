from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.payments.models import OutboxEvent, Payment
from app.payments.repository import SqlAlchemyPaymentRepository
from app.payments.schemas import CreatePaymentCommand, PaymentStatus


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


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
async def test_create_payment_with_outbox_persists_payment_and_event(session):
    repository = SqlAlchemyPaymentRepository(session)

    payment = await repository.create_payment_with_outbox(payment_command())

    stored_payment = await session.get(Payment, payment.payment_id)
    assert stored_payment is not None
    assert stored_payment.status == PaymentStatus.pending.value

    outbox_events = (await session.execute(OutboxEvent.__table__.select())).all()
    assert len(outbox_events) == 1
    assert outbox_events[0].payload == {"payment_id": str(payment.payment_id)}


@pytest.mark.asyncio
async def test_create_payment_with_outbox_returns_existing_payment_on_idempotency_race(session):
    repository = SqlAlchemyPaymentRepository(session)
    first = await repository.create_payment_with_outbox(payment_command("same-key"))

    second = await repository.create_payment_with_outbox(payment_command("same-key"))

    outbox_events = (await session.execute(OutboxEvent.__table__.select())).all()
    assert second == first
    assert len(outbox_events) == 1


@pytest.mark.asyncio
async def test_get_by_idempotency_key_returns_existing_payment(session):
    repository = SqlAlchemyPaymentRepository(session)
    created = await repository.create_payment_with_outbox(payment_command("same-key"))

    found = await repository.get_by_idempotency_key("same-key")

    assert found == created


@pytest.mark.asyncio
async def test_payment_database_constraints_reject_invalid_currency_and_status(session):
    session.add(
        Payment(
            amount=Decimal("125.50"),
            currency="BTC",
            description="Demo payment",
            metadata_={},
            status=PaymentStatus.pending.value,
            idempotency_key="bad-currency",
            webhook_url="https://example.com/webhook",
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()

    await session.rollback()
    session.add(
        Payment(
            amount=Decimal("125.50"),
            currency="RUB",
            description="Demo payment",
            metadata_={},
            status="unknown",
            idempotency_key="bad-status",
            webhook_url="https://example.com/webhook",
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
