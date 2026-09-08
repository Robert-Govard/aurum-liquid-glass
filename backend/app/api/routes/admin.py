from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_session
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate
from app.services.user_service import delete_user, list_users, update_user

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/users", response_model=list[UserRead])
async def list_users_route(session: AsyncSession = Depends(get_session)) -> list[User]:
    return await list_users(session)


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user_route(
    user_id: int, payload: UserUpdate, session: AsyncSession = Depends(get_session)
) -> User:
    return await update_user(session, user_id, payload)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user_route(user_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await delete_user(session, user_id)
