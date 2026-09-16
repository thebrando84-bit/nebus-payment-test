from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.messaging.outbox_publisher import publish_pending_outbox
from app.payments.models import OutboxEvent


class FakeBroker:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[tuple[dict[str, object], str]] = []

    async def publish(self, message, queue, persist: bool = False):
        if self.fail:
            raise RuntimeError("broker unavailable")
        self.messages.append((message, queue))


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_publish_pending_outbox_marks_event_published_after_broker_publish(session):
    event = OutboxEvent(event_type="payment.created", payload={"payment_id": "payment-1"})
    session.add(event)
    await session.commit()
    broker = FakeBroker()

    published = await publish_pending_outbox(session=session, broker=broker, limit=10)

    assert published == 1
    assert broker.messages == [({"payment_id": "payment-1"}, "payments.new")]
    assert event.published_at is not None
    assert event.published_at.tzinfo is not None


@pytest.mark.asyncio
async def test_publish_pending_outbox_leaves_event_unpublished_when_broker_fails(session):
    event = OutboxEvent(event_type="payment.created", payload={"payment_id": "payment-1"})
    session.add(event)
    await session.commit()

    with pytest.raises(RuntimeError, match="broker unavailable"):
        await publish_pending_outbox(session=session, broker=FakeBroker(fail=True), limit=10)

    await session.refresh(event)
    assert event.published_at is None


@pytest.mark.asyncio
async def test_publish_pending_outbox_skips_already_published_events(session):
    session.add(
        OutboxEvent(
            event_type="payment.created",
            payload={"payment_id": "payment-1"},
            published_at=datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
        )
    )
    await session.commit()
    broker = FakeBroker()

    published = await publish_pending_outbox(session=session, broker=broker, limit=10)

    assert published == 0
    assert broker.messages == []
