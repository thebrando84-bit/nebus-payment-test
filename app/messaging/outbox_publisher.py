from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.messaging.broker import PAYMENTS_NEW_QUEUE
from app.payments.models import OutboxEvent


class BrokerPublisher(Protocol):
    async def publish(self, message, queue, persist: bool = False): ...


async def publish_pending_outbox(
    *,
    session: AsyncSession,
    broker: BrokerPublisher,
    limit: int = 100,
) -> int:
    result = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(limit)
    )
    events = list(result.scalars())
    published = 0

    for event in events:
        await broker.publish(event.payload, queue=PAYMENTS_NEW_QUEUE, persist=True)
        event.published_at = datetime.now(UTC)
        published += 1

    await session.commit()
    return published
