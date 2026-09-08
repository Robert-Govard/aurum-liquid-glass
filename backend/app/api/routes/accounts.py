from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.account import AccountCreate, AccountUpdate, AccountWithBalance
from app.services.account_service import create_account, delete_account, list_accounts, update_account

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountWithBalance])
async def read_accounts(
    include_archived: bool = False,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[AccountWithBalance]:
    return await list_accounts(session, include_archived, current_user.id)


@router.post("", response_model=AccountWithBalance, status_code=201)
async def create_account_route(
    payload: AccountCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AccountWithBalance:
    return await create_account(session, payload, current_user.id)


@router.patch("/{account_id}", response_model=AccountWithBalance)
async def update_account_route(
    account_id: int,
    payload: AccountUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AccountWithBalance:
    return await update_account(session, account_id, payload, current_user.id)


@router.delete("/{account_id}", status_code=204)
async def delete_account_route(
    account_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    await delete_account(session, account_id, current_user.id)
