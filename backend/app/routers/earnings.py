import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Payment, User
from app.schemas import EarningCreditResponse, EarningsResponse
from app.security import get_current_user
from app.services.blockchain_service import read_pending_withdrawal

router = APIRouter()
logger = logging.getLogger(__name__)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@router.get("", response_model=EarningsResponse)
async def list_earnings(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EarningsResponse:
    """Return the authenticated provider's projected credit history."""
    if user.role != "provider":
        raise HTTPException(status_code=403, detail="Provider role required")

    result = await db.execute(
        select(Payment)
        .where(
            Payment.provider_id == user.id,
            Payment.payment_type == "provider_credit",
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
    )
    payments = result.scalars().all()

    pending_withdrawal: int | None = None
    pending_status = "unavailable"
    blockchain = request.app.state.blockchain
    if blockchain is not None and settings.NEBULA_PAYMENT_CONTRACT:
        try:
            pending_withdrawal = await run_in_threadpool(
                read_pending_withdrawal,
                blockchain,
                settings.NEBULA_PAYMENT_CONTRACT,
                user.wallet_address,
            )
            pending_status = "current"
        except Exception:
            # Contract/RPC internals must never be exposed through the browser API.
            logger.warning("Pending-withdrawal read failed", exc_info=True)

    return EarningsResponse(
        provider_id=str(user.id),
        total_credited_base_units=str(sum(int(payment.amount_base_units) for payment in payments)),
        total_withdrawn_base_units=str(
            sum(int(payment.amount_base_units) for payment in payments if payment.status == "withdrawn")
        ),
        pending_withdrawal_base_units=str(pending_withdrawal) if pending_withdrawal is not None else None,
        pending_withdrawal_status=pending_status,
        credits=[
            EarningCreditResponse(
                job_id=str(payment.job_id),
                amount_base_units=str(int(payment.amount_base_units)),
                status=payment.status or "pending",
                blockchain_tx_hash=payment.blockchain_tx_hash,
                withdrawal_tx_hash=payment.withdrawal_tx_hash,
                credited_at=_as_utc(payment.credited_at),
                withdrawn_at=_as_utc(payment.withdrawn_at),
            )
            for payment in payments
        ],
    )
