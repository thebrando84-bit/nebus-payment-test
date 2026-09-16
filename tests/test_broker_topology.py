from app.messaging.broker import (
    PAYMENTS_DLQ,
    PAYMENTS_DLX,
    declare_payment_topology,
    payments_new_queue,
)


class FakeDeclaredQueue:
    def __init__(self) -> None:
        self.binds = []

    async def bind(self, exchange, routing_key: str) -> None:
        self.binds.append((exchange, routing_key))


class FakeBroker:
    def __init__(self) -> None:
        self.exchanges = []
        self.queues = []
        self.dlq = FakeDeclaredQueue()

    async def declare_exchange(self, exchange):
        self.exchanges.append(exchange)
        return exchange

    async def declare_queue(self, queue):
        self.queues.append(queue)
        if queue.name == PAYMENTS_DLQ:
            return self.dlq
        return FakeDeclaredQueue()


def test_payments_new_queue_routes_to_dlq_after_three_delivery_attempts():
    assert payments_new_queue.arguments["x-delivery-limit"] == 3
    assert payments_new_queue.arguments["x-dead-letter-exchange"] == PAYMENTS_DLX
    assert payments_new_queue.arguments["x-dead-letter-routing-key"] == PAYMENTS_DLQ


async def test_declare_payment_topology_declares_and_binds_dlq():
    broker = FakeBroker()

    await declare_payment_topology(broker)

    assert [exchange.name for exchange in broker.exchanges] == [PAYMENTS_DLX]
    assert [queue.name for queue in broker.queues] == [PAYMENTS_DLQ, "payments.new"]
    assert broker.dlq.binds == [(broker.exchanges[0], PAYMENTS_DLQ)]
