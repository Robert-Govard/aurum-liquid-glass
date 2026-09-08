"""Auth: registration, login, token refresh/rotation, logout."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.refresh_token import RefreshToken
from app.models.user import User


async def test_user_and_refresh_token_tables_exist(test_sessionmaker):
    async with test_sessionmaker() as session:
        session.add(User(email="probe@example.com", password_hash="x"))
        await session.flush()
        user_id = (await session.execute(select(User.id).where(User.email == "probe@example.com"))).scalar_one()
        expires_at = datetime(2030, 1, 1, tzinfo=timezone.utc)
        session.add(RefreshToken(user_id=user_id, token_hash="y" * 64, expires_at=expires_at))
        await session.commit()

        stored = (await session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id))).scalar_one()
        assert stored.revoked_at is None
