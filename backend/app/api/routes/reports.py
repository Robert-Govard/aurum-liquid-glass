from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.enums import CategoryKind
from app.models.user import User
from app.schemas.reports import CategoryRankingReport, CategorySpendingReport
from app.services.reports_service import get_category_ranking_report, get_category_spending_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/category-spending", response_model=CategorySpendingReport)
async def read_category_spending_report(
    category_id: int,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CategorySpendingReport:
    return await get_category_spending_report(session, category_id, start_date, end_date, current_user.id)


@router.get("/category-ranking", response_model=CategoryRankingReport)
async def read_category_ranking_report(
    kind: CategoryKind = CategoryKind.EXPENSE,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CategoryRankingReport:
    return await get_category_ranking_report(session, kind, start_date, end_date, current_user.id)
