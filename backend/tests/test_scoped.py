"""Unit tests for the shared scoped-query helper every user-owned-table
service routes through (see services/scoped.py)."""
from fastapi import HTTPException
from sqlalchemy import select
import pytest

from app.models.account import Account
from app.models.enums import AccountType
from app.models.user import User
from app.services.scoped import get_owned_or_404, scoped


async def _make_user(session, email: str) -> User:
    """`Account.user_id` is a real foreign key to `users.id` — these tests
    insert Account rows directly (bypassing the HTTP API), so they need a
    real User row to point at, not just an arbitrary integer."""
    user = User(email=email, password_hash="x")
    session.add(user)
    await session.flush()
    return user


async def test_scoped_only_returns_the_given_users_rows(test_sessionmaker):
    async with test_sessionmaker() as session:
        user_a = await _make_user(session, "scoped-a@example.com")
        user_b = await _make_user(session, "scoped-b@example.com")
        session.add_all(
            [
                Account(name="A's account", type=AccountType.CHECKING, currency="USD", user_id=user_a.id),
                Account(name="B's account", type=AccountType.CHECKING, currency="USD", user_id=user_b.id),
            ]
        )
        await session.commit()

        stmt = scoped(select(Account), Account, user_id=user_a.id)
        rows = (await session.execute(stmt)).scalars().all()
        assert [a.name for a in rows] == ["A's account"]


async def test_get_owned_or_404_returns_the_row_when_owned(test_sessionmaker):
    async with test_sessionmaker() as session:
        user = await _make_user(session, "owned@example.com")
        account = Account(name="Mine", type=AccountType.CHECKING, currency="USD", user_id=user.id)
        session.add(account)
        await session.commit()

        found = await get_owned_or_404(session, Account, account.id, user_id=user.id)
        assert found.id == account.id


async def test_get_owned_or_404_404s_for_someone_elses_row(test_sessionmaker):
    async with test_sessionmaker() as session:
        owner = await _make_user(session, "owner@example.com")
        other = await _make_user(session, "other@example.com")
        account = Account(name="Theirs", type=AccountType.CHECKING, currency="USD", user_id=owner.id)
        session.add(account)
        await session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await get_owned_or_404(session, Account, account.id, user_id=other.id)
        assert exc_info.value.status_code == 404


async def test_get_owned_or_404_404s_for_a_nonexistent_id(test_sessionmaker):
    async with test_sessionmaker() as session:
        user = await _make_user(session, "nonexistent-id@example.com")
        with pytest.raises(HTTPException) as exc_info:
            await get_owned_or_404(session, Account, 999999, user_id=user.id)
        assert exc_info.value.status_code == 404
