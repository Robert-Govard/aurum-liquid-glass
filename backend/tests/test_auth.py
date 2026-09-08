"""Auth: registration, login, token refresh/rotation, logout."""
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core import security
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


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", "test-secret-do-not-use-in-prod")


def test_password_hash_roundtrip():
    hashed = security.hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert security.verify_password("correct horse battery staple", hashed)
    assert not security.verify_password("wrong password", hashed)


def test_access_token_roundtrip():
    token = security.create_access_token(user_id=42)
    assert security.decode_access_token(token) == 42


def test_access_token_rejects_tampering():
    token = security.create_access_token(user_id=42)
    with pytest.raises(pyjwt.PyJWTError):
        security.decode_access_token(token + "x")


def test_access_token_rejects_expired():
    now = datetime.now(timezone.utc)
    payload = {"sub": "42", "type": "access", "iat": now, "exp": now - timedelta(seconds=1)}
    expired = pyjwt.encode(payload, get_settings().jwt_secret, algorithm=security.JWT_ALGORITHM)
    with pytest.raises(pyjwt.PyJWTError):
        security.decode_access_token(expired)


def test_refresh_token_roundtrip_and_hash():
    raw, token_hash, expires_at = security.create_refresh_token(user_id=7)
    assert security.decode_refresh_token(raw) == 7
    assert security.hash_token(raw) == token_hash
    assert expires_at > datetime.now(timezone.utc)


def test_access_token_rejected_by_decode_refresh_token():
    access = security.create_access_token(user_id=1)
    with pytest.raises(pyjwt.PyJWTError):
        security.decode_refresh_token(access)
