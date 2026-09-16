# Асинхронный сервис обработки платежей

Тестовое задание: backend-сервис для асинхронной обработки платежей.


## Технологии

- Python 3.12
- FastAPI + Pydantic v2
- SQLAlchemy 2.0 в async-режиме + asyncpg
- PostgreSQL
- RabbitMQ + FastStream
- Alembic
- httpx
- Docker Compose
- pytest

## Быстрый запуск

```bash
cp .env.example .env
docker compose up --build
```

После запуска API будет доступно по адресу:

```text
http://localhost:8000
```

RabbitMQ Management UI:

```text
http://localhost:15672
```

Логин и пароль RabbitMQ по умолчанию:

```text
guest / guest
```

## Примеры запросов

Создать платеж:

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: dev-api-key" \
  -H "Idempotency-Key: demo-001" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "125.50",
    "currency": "RUB",
    "description": "Тестовый платеж",
    "metadata": {"order_id": "1"},
    "webhook_url": "https://webhook.site/<your-id>"
  }'
```

Получить информацию о платеже:

```bash
curl http://localhost:8000/api/v1/payments/<payment_id> \
  -H "X-API-Key: dev-api-key"
```

## Как устроен поток обработки

1. Клиент отправляет `POST /api/v1/payments`.
2. API проверяет `X-API-Key` и валидирует тело запроса.
3. `PaymentService` проверяет `Idempotency-Key`.
4. `SqlAlchemyPaymentRepository` создает запись в `payments` и событие в `outbox` в одной транзакции.
5. Сервис `migrate` применяет Alembic-миграции до запуска API и worker-сервисов.
6. `outbox-publisher` забирает неопубликованные события из `outbox` и публикует их в RabbitMQ queue `payments.new`.
7. `consumer` получает сообщение, эмулирует обработку платежа 2-5 секунд, обновляет статус на `succeeded` или `failed` и отправляет webhook.
8. Webhook отправляется с 3 попытками и экспоненциальной задержкой между попытками.

## Надежность и гарантии

- Идемпотентность создания платежа обеспечивается уникальным `payments.idempotency_key` и проверкой в сервисном слое.
- Outbox pattern используется, чтобы создание платежа и создание события были атомарными.
- `outbox-publisher` выставляет `published_at` только после успешной публикации события в RabbitMQ.
- RabbitMQ-топология явно объявляет `payments.new`, `payments.dlx` и `payments.dlq`.
- `payments.new` настроена как quorum queue с `x-delivery-limit=3`.
- Consumer идемпотентен для повторной доставки: финальные статусы `succeeded` и `failed` не переигрываются.
- Если сообщение некорректное, платеж не найден или webhook не доставлен после всех попыток, consumer падает на сообщении, чтобы RabbitMQ мог выполнить retry и затем отправить сообщение в DLQ.

## Что намеренно не добавлено

- Kubernetes-манифесты;
- полноценный стек метрик и трассировки;
- отдельный сервис авторизации;
- интеграция с реальным платежным провайдером;
- admin panel;
- распределенные locks;
- обещания exactly-once delivery.

Для production версии я бы добавил structured logging, request id, метрики, tracing, publisher confirms, `SELECT FOR UPDATE SKIP LOCKED` для масштабирования outbox publisher-ов, безопасное хранение секретов, CI и нагрузочные тесты.

## Локальная разработка

Создать виртуальное окружение и установить зависимости:

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e . pytest pytest-asyncio aiosqlite
```

Запустить тесты:

```bash
.venv\Scripts\python.exe -m pytest -v
```

Применить миграции локально к настроенной PostgreSQL-базе:

```bash
alembic upgrade head
```
