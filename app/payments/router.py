from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.db.session import get_session
from app.payments.repository import SqlAlchemyPaymentRepository
from app.payments.schemas import CreatePaymentCommand, PaymentCreateRequest, PaymentDetail
from app.payments.service import PaymentService


class PaymentServiceProtocol(Protocol):
    async def create_payment(self, *, command: CreatePaymentCommand) -> PaymentDetail: ...

    async def get_payment(self, *, payment_id: UUID) -> PaymentDetail | None: ...


SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


def get_payment_service(session: SessionDep) -> PaymentServiceProtocol:
    return PaymentService(repository=SqlAlchemyPaymentRepository(session))


PaymentServiceDep = Annotated[PaymentServiceProtocol, Depends(get_payment_service)]

router = APIRouter(prefix="/api/v1/payments", tags=["payments"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=PaymentDetail, status_code=status.HTTP_202_ACCEPTED)
async def create_payment(
    payload: PaymentCreateRequest,
    idempotency_key: IdempotencyKey,
    service: PaymentServiceDep,
) -> PaymentDetail:
    command = CreatePaymentCommand(
        amount=payload.amount,
        currency=payload.currency,
        description=payload.description,
        metadata=payload.metadata,
        webhook_url=str(payload.webhook_url),
        idempotency_key=idempotency_key,
    )
    return await service.create_payment(command=command)


@router.get("/{payment_id}", response_model=PaymentDetail)
async def get_payment(
    payment_id: UUID,
    service: PaymentServiceDep,
) -> PaymentDetail:
    payment = await service.get_payment(payment_id=payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment

