"""Test harness wiring.

Everything here talks to a dedicated ``aurum_test`` Postgres database on the
same server the app already uses — created fresh, migrated with the real
Alembic chain, and dropped again at the end of the run. The app's own
``AsyncSessionLocal``/``lifespan`` (which would touch the real ``aurum``
database with the user's actual financial history) is never invoked: the
ASGI app is exercised directly over httpx without running startup events,
and the ``get_session`` dependency is overridden per-test to point at the
test database instead. See tests/README.md for how to run this.
"""
import asyncio
import os
import subprocess
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_session
from app.core.config import get_settings
from app.db.base import Base
from app.main import app
from app.models.user import User

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_NAME = "aurum_test"

_base_settings = get_settings()


def _url(db_name: str) -> str:
    return (
        f"postgresql+asyncpg://{_base_settings.postgres_user}:{_base_settings.postgres_password}"
        f"@{_base_settings.postgres_host}:{_base_settings.postgres_port}/{db_name}"
    )


async def _drop_and_create_test_database() -> None:
    engine = create_async_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    await engine.dispose()


async def _drop_test_database() -> None:
    engine = create_async_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
    await engine.dispose()


@pytest.fixture(scope="session")
def _test_database() -> Generator[None, None, None]:
    """Create aurum_test from scratch and run every Alembic migration
    against it. Connects to Postgres' always-present `postgres` maintenance
    database to issue CREATE/DROP DATABASE — the real `aurum` database is
    never opened by this fixture.

    Deliberately a *sync* fixture that drives asyncio.run() itself rather
    than an async one: session-scoped async fixtures need to share a loop
    with function-scoped async tests, which pytest-asyncio doesn't do by
    default and led to "attached to a different loop" errors here. A plain
    sync fixture sidesteps the whole question — asyncio.run() opens and
    cleanly closes its own throwaway loop for each of the two calls below.
    """
    asyncio.run(_drop_and_create_test_database())

    env = {**os.environ, "AURUM_POSTGRES_DB": TEST_DB_NAME}
    subprocess.run(["alembic", "upgrade", "head"], cwd=BACKEND_DIR, env=env, check=True)

    yield

    asyncio.run(_drop_test_database())


@pytest_asyncio.fixture
async def test_sessionmaker(_test_database) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    # Function-scoped, not session-scoped: pytest-asyncio gives each test
    # function its own event loop, and an asyncpg engine/pool created under
    # one loop can't be reused from another ("attached to a different
    # loop"). Recreating the engine per test keeps it bound to whichever
    # loop is actually running.
    engine = create_async_engine(_url(TEST_DB_NAME), pool_pre_ping=True)
    yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_database(test_sessionmaker):
    """Wipe every table before each test — no instance-wide seeding
    happens anymore; each test's `client` fixture registers its own user,
    whose categories/settings are seeded by that registration call, same
    as a real signup."""
    async with test_sessionmaker() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
        await session.commit()
    yield


@pytest_asyncio.fixture
async def client(test_sessionmaker) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api") as ac:
        register_resp = await ac.post("/auth/register", json={"email": "test@example.com", "password": "hunter22"})
        assert register_resp.status_code == 201, register_resp.text

        # Registration alone no longer creates a session — a real account
        # needs its email verified first (see services/auth_service.py).
        # Flip it directly here rather than actually sending/reading an
        # email: this fixture just needs a working default user, not a
        # test of the verification flow itself (see test_auth.py for that).
        async with test_sessionmaker() as session:
            await session.execute(
                update(User).where(User.email == "test@example.com").values(is_email_verified=True)
            )
            await session.commit()

        login_resp = await ac.post("/auth/login", json={"email": "test@example.com", "password": "hunter22"})
        assert login_resp.status_code == 200, login_resp.text
        token = login_resp.json()["access_token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def account_id(client: AsyncClient) -> int:
    """Creates one account for the test's default user (see the `client`
    fixture) — every transaction needs one, and there's no more
    auto-seeded account (registration only seeds categories/settings)."""
    resp = await client.post("/accounts", json={"name": "Main Account", "type": "checking", "currency": "USD"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest_asyncio.fixture
async def categories(client: AsyncClient) -> dict[str, dict]:
    """Default seeded categories keyed by name, e.g. categories["Groceries"]["id"]."""
    resp = await client.get("/categories")
    return {c["name"]: c for c in resp.json()}
