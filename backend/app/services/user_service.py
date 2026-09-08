"""Admin operations on User rows — list/disable/delete. No self-service
"become admin" path exists by design; see scripts/promote_admin.py for how
the first admin is created."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import UserUpdate


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


async def update_user(session: AsyncSession, user_id: int, payload: UserUpdate) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Only a True -> False transition should touch tokens: re-enabling a user
    # shouldn't hand back their old sessions, and re-saving an already
    # disabled user shouldn't re-run this (harmless, but pointless) query.
    is_disabling = user.is_active and not payload.is_active
    user.is_active = payload.is_active
    if is_disabling:
        # Disabling a user should kill their live sessions immediately, not
        # just rely on auth_service.refresh()'s own is_active check to reject
        # them lazily on next use — an admin disabling someone expects it to
        # take effect now. Same revoke-in-place pattern as auth_service's
        # logout().
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user_id: int) -> None:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()
