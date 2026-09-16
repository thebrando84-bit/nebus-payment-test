from typing import Protocol

from faststream.rabbit import QueueType, RabbitBroker, RabbitExchange, RabbitQueue

from app.core.config import get_settings

PAYMENTS_NEW_QUEUE = "payments.new"
PAYMENTS_DLX = "payments.dlx"
PAYMENTS_DLQ = "payments.dlq"

payments_dlx = RabbitExchange(PAYMENTS_DLX, durable=True)
payments_new_queue = RabbitQueue(
    PAYMENTS_NEW_QUEUE,
    queue_type=QueueType.QUORUM,
    durable=True,
    arguments={
        "x-delivery-limit": 3,
        "x-dead-letter-exchange": PAYMENTS_DLX,
        "x-dead-letter-routing-key": PAYMENTS_DLQ,
    },
)
payments_dlq = RabbitQueue(PAYMENTS_DLQ, durable=True)


class TopologyBroker(Protocol):
    async def declare_exchange(self, exchange: RabbitExchange): ...

    async def declare_queue(self, queue: RabbitQueue): ...


async def declare_payment_topology(broker: TopologyBroker) -> None:
    dlx = await broker.declare_exchange(payments_dlx)
    dlq = await broker.declare_queue(payments_dlq)
    await dlq.bind(dlx, routing_key=PAYMENTS_DLQ)
    await broker.declare_queue(payments_new_queue)


broker = RabbitBroker(get_settings().rabbitmq_url)
