from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_session
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.schemas.user import AdminUserRead, UserRead, UserUpdate
from app.services.dashboard_service import get_dashboard_summary
from app.services.user_service import delete_user, list_users, update_user

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/users", response_model=list[AdminUserRead])
async def list_users_route(session: AsyncSession = Depends(get_session)) -> list[AdminUserRead]:
    return await list_users(session)


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user_route(
    user_id: int,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    current_admin: User = Depends(get_current_admin),
) -> User:
    return await update_user(session, user_id, payload, current_admin.id)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user_route(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    current_admin: User = Depends(get_current_admin),
) -> None:
    await delete_user(session, user_id, current_admin.id)


@router.get("/users/{user_id}/dashboard-summary", response_model=DashboardSummary)
async def user_dashboard_summary_route(
    user_id: int,
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> DashboardSummary:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return await get_dashboard_summary(session, year, month, user_id)
