"""Auth: registration, login, token refresh/rotation, logout."""
import asyncio
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core import security
from app.models.category import Category
from app.models.refresh_token import RefreshToken
from app.models.settings import AppSettings
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


async def test_register_returns_token_pair(client):
    resp = await client.post("/auth/register", json={"email": "a@example.com", "password": "hunter22"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]


async def test_register_rejects_duplicate_email(client):
    await client.post("/auth/register", json={"email": "dup@example.com", "password": "hunter22"})
    resp = await client.post("/auth/register", json={"email": "dup@example.com", "password": "different1"})
    assert resp.status_code == 409


async def test_login_with_correct_password(client):
    await client.post("/auth/register", json={"email": "b@example.com", "password": "hunter22"})
    resp = await client.post("/auth/login", json={"email": "b@example.com", "password": "hunter22"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_with_wrong_password(client):
    await client.post("/auth/register", json={"email": "c@example.com", "password": "hunter22"})
    resp = await client.post("/auth/login", json={"email": "c@example.com", "password": "wrong-password"})
    assert resp.status_code == 401


async def test_login_with_unknown_email(client):
    resp = await client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever1"})
    assert resp.status_code == 401


async def test_refresh_issues_new_pair_and_rotates(client):
    register_resp = await client.post("/auth/register", json={"email": "d@example.com", "password": "hunter22"})
    old_refresh = register_resp.json()["refresh_token"]

    refresh_resp = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_resp.status_code == 200
    new_refresh = refresh_resp.json()["refresh_token"]
    assert new_refresh != old_refresh

    # the rotated-out token must no longer work
    reuse_resp = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse_resp.status_code == 401

    # the new one does
    second_refresh_resp = await client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert second_refresh_resp.status_code == 200


async def test_refresh_rejects_garbage_token(client):
    resp = await client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


async def test_concurrent_refresh_of_the_same_token_only_one_wins(client):
    """Regression test for the rotation race: two concurrent presentations
    of the same still-valid refresh token must not both succeed. The
    atomic conditional UPDATE in auth_service.refresh() (WHERE
    revoked_at IS NULL, checked and set in one statement) means Postgres
    serializes the two UPDATEs via row locking — the loser's WHERE clause
    finds the row already revoked and matches zero rows, so exactly one
    request gets a new token pair and the other is rejected."""
    register_resp = await client.post("/auth/register", json={"email": "f@example.com", "password": "hunter22"})
    old_refresh = register_resp.json()["refresh_token"]

    first_resp, second_resp = await asyncio.gather(
        client.post("/auth/refresh", json={"refresh_token": old_refresh}),
        client.post("/auth/refresh", json={"refresh_token": old_refresh}),
    )

    statuses = sorted([first_resp.status_code, second_resp.status_code])
    assert statuses == [200, 401], f"expected exactly one winner and one rejection, got {statuses}"


async def test_logout_revokes_the_refresh_token(client):
    register_resp = await client.post("/auth/register", json={"email": "e@example.com", "password": "hunter22"})
    refresh_token = register_resp.json()["refresh_token"]

    logout_resp = await client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 204

    reuse_resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_resp.status_code == 401


async def test_register_seeds_the_new_users_own_categories_and_settings(client, test_sessionmaker):
    resp = await client.post("/auth/register", json={"email": "seeded@example.com", "password": "hunter22"})
    tokens = resp.json()

    me_resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me_resp.status_code == 200
    user_id = me_resp.json()["id"]

    async with test_sessionmaker() as session:
        categories = (await session.execute(select(Category).where(Category.user_id == user_id))).scalars().all()
        assert len(categories) == 17  # 8 expense + 9 income, see DEFAULT_*_CATEGORIES in db/seed.py

        settings_row = (
            await session.execute(select(AppSettings).where(AppSettings.user_id == user_id))
        ).scalar_one()
        assert settings_row.currency  # created, not left missing


async def test_get_me_requires_auth(client):
    # The client fixture's default Authorization header is valid — override
    # it with an empty one for this one call to simulate no token at all.
    resp = await client.get("/auth/me", headers={"Authorization": ""})
    assert resp.status_code == 401


async def test_login_and_register_set_last_login_at(client, test_sessionmaker):
    resp = await client.post("/auth/register", json={"email": "lastlogin@example.com", "password": "hunter22"})
    assert resp.status_code == 201

    async with test_sessionmaker() as session:
        result = await session.execute(select(User).where(User.email == "lastlogin@example.com"))
        user = result.scalar_one()
        assert user.last_login_at is not None
        first_login = user.last_login_at

    login_resp = await client.post("/auth/login", json={"email": "lastlogin@example.com", "password": "hunter22"})
    assert login_resp.status_code == 200

    async with test_sessionmaker() as session:
        result = await session.execute(select(User).where(User.email == "lastlogin@example.com"))
        user = result.scalar_one()
        assert user.last_login_at is not None
        assert user.last_login_at >= first_login


async def test_get_me_returns_the_callers_own_email(client):
    # NOTE: the task-3 brief's version of this test called `client.get("/auth/me")`
    # with no explicit token, relying on the `client` fixture setting a default
    # Authorization header for its one auto-registered user. That default header
    # is only added in Task 4's conftest.py rewrite (tests/helpers.py /
    # conftest.py are explicitly out of scope for this task — see task-3-brief.md
    # step 4/task-4-brief.md step 1) — today's `client` fixture sends no
    # Authorization header at all. Registering explicitly here keeps this test
    # passing now instead of silently depending on infrastructure that doesn't
    # exist yet; it verifies the same thing (`/auth/me` returns the caller's own
    # email, never the password/hash).
    register_resp = await client.post("/auth/register", json={"email": "whoami@example.com", "password": "hunter22"})
    token = register_resp.json()["access_token"]

    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "email" in body
    assert "password" not in body and "password_hash" not in body
