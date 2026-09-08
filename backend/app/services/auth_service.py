"""Registration/login/token-refresh/logout — the only place that issues or
revokes tokens; routes/auth.py stays a thin HTTP wrapper around this."""
from datetime import datetime, timezone

import jwt
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenPair


async def _issue_token_pair(session: AsyncSession, user_id: int) -> TokenPair:
    access = create_access_token(user_id)
    raw_refresh, refresh_hash, expires_at = create_refresh_token(user_id)
    session.add(RefreshToken(user_id=user_id, token_hash=refresh_hash, expires_at=expires_at))
    await session.commit()
    return TokenPair(access_token=access, refresh_token=raw_refresh)


async def register(session: AsyncSession, payload: RegisterRequest) -> TokenPair:
    existing = await session.execute(select(User.id).where(User.email == payload.email))
    if existing.first() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    await session.flush()  # assigns user.id without ending the transaction
    return await _issue_token_pair(session, user.id)


async def login(session: AsyncSession, email: str, password: str) -> TokenPair:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return await _issue_token_pair(session, user.id)


async def refresh(session: AsyncSession, raw_token: str) -> TokenPair:
    try:
        user_id = decode_refresh_token(raw_token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None

    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    # Atomic conditional UPDATE, not select-then-mutate-then-commit-later:
    # the "is this token still valid" check and the revocation itself have
    # to happen as one database operation, or two concurrent presentations
    # of the same still-valid token (a race, or a client retry) could both
    # read revoked_at IS NULL before either commits and both walk away with
    # a live child pair — defeating rotation. Only one concurrent caller can
    # match revoked_at.is_(None) here; the other gets rowcount == 0. Same
    # pattern as logout() below.
    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at >= now,
        )
        .values(revoked_at=now)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=401, detail="Refresh token is no longer valid")

    return await _issue_token_pair(session, user_id)


async def logout(session: AsyncSession, raw_token: str) -> None:
    token_hash = hash_token(raw_token)
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await session.commit()
