import asyncio

from app.db.session import SessionLocal
from app.messaging.broker import broker, declare_payment_topology
from app.messaging.outbox_publisher import publish_pending_outbox


async def run_outbox_worker(*, poll_interval_seconds: float = 1.0, batch_size: int = 100) -> None:
    await broker.start()
    await declare_payment_topology(broker)
    try:
        while True:
            async with SessionLocal() as session:
                await publish_pending_outbox(session=session, broker=broker, limit=batch_size)
            await asyncio.sleep(poll_interval_seconds)
    finally:
        await broker.stop()


if __name__ == "__main__":
    asyncio.run(run_outbox_worker())

