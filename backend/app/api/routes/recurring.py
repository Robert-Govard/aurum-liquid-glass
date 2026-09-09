from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.recurring import RecurringTransactionCreate, RecurringTransactionRead, RecurringTransactionUpdate
from app.services.recurring_service import (
    create_recurring,
    delete_recurring,
    list_recurring,
    post_recurring,
    update_recurring,
)

router = APIRouter(prefix="/recurring", tags=["recurring"])


@router.get("", response_model=list[RecurringTransactionRead])
async def read_recurring(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> list[RecurringTransactionRead]:
    return await list_recurring(session, current_user.id)


@router.post("", response_model=RecurringTransactionRead, status_code=201)
async def create_recurring_route(
    payload: RecurringTransactionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringTransactionRead:
    return await create_recurring(session, payload, current_user.id)


@router.patch("/{recurring_id}", response_model=RecurringTransactionRead)
async def update_recurring_route(
    recurring_id: int,
    payload: RecurringTransactionUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringTransactionRead:
    return await update_recurring(session, recurring_id, payload, current_user.id)


@router.delete("/{recurring_id}", status_code=204)
async def delete_recurring_route(
    recurring_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    await delete_recurring(session, recurring_id, current_user.id)


@router.post("/{recurring_id}/post", response_model=RecurringTransactionRead, status_code=201)
async def post_recurring_route(
    recurring_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringTransactionRead:
    return await post_recurring(session, recurring_id, current_user.id)
