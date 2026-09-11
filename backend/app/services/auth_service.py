"""Registration/login/token-refresh/logout/email-verification — the only
place that issues or revokes tokens; routes/auth.py stays a thin HTTP
wrapper around this."""
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import BackgroundTasks, HTTPException
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
from app.db.seed import seed_default_app_settings, seed_default_categories
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import MessageResponse, RegisterRequest, TokenPair
from app.services.email_service import send_verification_email

EMAIL_VERIFICATION_TOKEN_TTL = timedelta(hours=24)


async def _issue_token_pair(session: AsyncSession, user_id: int) -> TokenPair:
    access = create_access_token(user_id)
    raw_refresh, refresh_hash, expires_at = create_refresh_token(user_id)
    session.add(RefreshToken(user_id=user_id, token_hash=refresh_hash, expires_at=expires_at))
    await session.commit()
    return TokenPair(access_token=access, refresh_token=raw_refresh)


def _issue_verification_token(user: User) -> str:
    """Mutates `user` in place (caller commits) and returns the RAW token
    to email to the user — only its SHA-256 hash is ever persisted (see
    core/security.py's hash_token, the same scheme refresh tokens use).
    A new call always overwrites the previous token: only one verification
    token is ever outstanding per user."""
    raw_token = secrets.token_urlsafe(32)
    user.email_verification_token_hash = hash_token(raw_token)
    user.email_verification_expires_at = datetime.now(timezone.utc) + EMAIL_VERIFICATION_TOKEN_TTL
    return raw_token


async def register(
    session: AsyncSession, payload: RegisterRequest, background_tasks: BackgroundTasks
) -> MessageResponse:
    result = await session.execute(select(User).where(User.email == payload.email))
    existing = result.scalar_one_or_none()

    if existing is not None:
        if existing.is_email_verified or not verify_password(payload.password, existing.password_hash):
            # Same response whether the email is already verified or the
            # password just doesn't match this unverified account —
            # otherwise the response would let a caller tell verified
            # accounts apart from unverified ones by trying a password.
            raise HTTPException(status_code=409, detail="Email already registered")
        # Unverified account, correct password: resend instead of 409 —
        # this is also exactly what the frontend's "send again" button
        # calls (see spec: no separate resend endpoint).
        raw_token = _issue_verification_token(existing)
        await session.commit()
        background_tasks.add_task(send_verification_email, existing.email, raw_token)
        return MessageResponse(message="Verification email sent")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    await session.flush()  # assigns user.id without ending the transaction

    await seed_default_categories(session, user.id)
    await seed_default_app_settings(session, user.id)

    raw_token = _issue_verification_token(user)
    await session.commit()
    background_tasks.add_task(send_verification_email, user.email, raw_token)
    return MessageResponse(message="Verification email sent")


async def login(session: AsyncSession, email: str, password: str) -> TokenPair:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_email_verified:
        # Checked AFTER the password check on purpose — a wrong password on
        # an unverified account must still look like a generic 401, not
        # hint that the account exists but isn't verified yet.
        raise HTTPException(status_code=403, detail="Email not verified")
    user.last_login_at = datetime.now(timezone.utc)
    return await _issue_token_pair(session, user.id)


async def verify_email(session: AsyncSession, raw_token: str) -> TokenPair:
    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(User).where(
            User.email_verification_token_hash == token_hash,
            User.email_verification_expires_at >= now,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user.is_email_verified = True
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    # The only place a brand-new user's last_login_at gets set for the
    # first time — register() no longer counts as a login since it no
    # longer issues a session; this does, immediately (see spec: "перешёл
    # по ссылке — и уже внутри приложения").
    user.last_login_at = now
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
    #
    # The `user_id.in_(active_user_ids)` clause folds in the "owning user is
    # still active" check without a separate SELECT: a disabled user's
    # refresh token must stop working immediately (see user_service's
    # update_user, which also revokes outstanding tokens the moment a user
    # is disabled — this is the lazy backstop for any token issued in the
    # narrow window around that), and doing it as a subquery inside the same
    # UPDATE keeps everything above atomic instead of reintroducing a
    # load-then-check race.
    active_user_ids = select(User.id).where(User.id == user_id, User.is_active.is_(True))
    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at >= now,
            RefreshToken.user_id.in_(active_user_ids),
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
