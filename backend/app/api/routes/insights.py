from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.insights import AlertsResponse
from app.services.insights_service import get_financial_alerts

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/alerts", response_model=AlertsResponse)
async def read_financial_alerts(session: AsyncSession = Depends(get_session)) -> AlertsResponse:
    return await get_financial_alerts(session)
