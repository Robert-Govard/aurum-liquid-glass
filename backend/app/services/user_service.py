"""Admin operations on User rows — list/disable/delete. No self-service
"become admin" path exists by design; see scripts/promote_admin.py for how
the first admin is created."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import AdminUserRead, UserPremiumUpdate, UserUpdate
from app.services.admin_stats_service import UserStats, get_user_currencies, get_user_stats


async def list_users(session: AsyncSession) -> list[AdminUserRead]:
    result = await session.execute(select(User).order_by(User.created_at))
    users = list(result.scalars().all())
    stats = await get_user_stats(session)
    currencies = await get_user_currencies(session)
    empty_stats = UserStats()
    return [
        AdminUserRead(
            id=user.id,
            email=user.email,
            is_admin=user.is_admin,
            is_active=user.is_active,
            is_premium=user.is_premium,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            accounts_count=stats.get(user.id, empty_stats).accounts_count,
            transactions_count=stats.get(user.id, empty_stats).transactions_count,
            net_worth=stats.get(user.id, empty_stats).net_worth,
            currency=currencies.get(user.id, "USD"),
            premium_until=user.premium_until,
        )
        for user in users
    ]


async def update_user(session: AsyncSession, user_id: int, payload: UserUpdate, acting_admin_id: int) -> User:
    if user_id == acting_admin_id:
        raise HTTPException(status_code=400, detail="Cannot modify your own account")
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


async def delete_user(session: AsyncSession, user_id: int, acting_admin_id: int) -> None:
    if user_id == acting_admin_id:
        raise HTTPException(status_code=400, detail="Cannot modify your own account")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()


async def update_user_premium(session: AsyncSession, user_id: int, payload: UserPremiumUpdate) -> User:
    """No self-lockout guard here (unlike update_user()/delete_user()):
    an admin setting their own premium_until has zero effect either way
    — User.is_premium already returns True for any admin regardless of
    this field — so there is nothing destructive to guard against."""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.premium_until = payload.premium_until
    await session.commit()
    await session.refresh(user)
    return user
