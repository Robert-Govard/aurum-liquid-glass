from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.cash_flow import CashFlowResponse
from app.services.cash_flow_service import get_cash_flow

router = APIRouter(prefix="/cash-flow", tags=["cash-flow"])


@router.get("", response_model=CashFlowResponse)
async def read_cash_flow(
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CashFlowResponse:
    return await get_cash_flow(session, start_date, end_date, current_user.id)
