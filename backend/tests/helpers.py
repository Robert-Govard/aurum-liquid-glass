"""Shared test fixtures' plain-Python helpers (not pytest fixtures
themselves — those live in conftest.py)."""
from decimal import Decimal


def money(value) -> Decimal:
    """Compares amounts by value regardless of whether the API serializes
    Decimal as a JSON string or number — that's a wire-format detail, not
    business behavior worth pinning a test to."""
    return Decimal(str(value))


def txn_payload(account_id: int, **overrides) -> dict:
    payload = {
        "account_id": account_id,
        "type": "expense",
        "amount": "10.00",
        "description": "test transaction",
        "date": "2026-01-15",
    }
    payload.update(overrides)
    return payload


async def register_user(client, email: str, password: str = "hunter22") -> dict:
    """Registers a second user for an isolation test (the `client` fixture
    already auto-registers and authenticates as one default user — use
    this to bring in another one and compare what each can/can't see).
    Returns a real TokenPair dict (access_token, refresh_token, token_type)
    for that user: registration alone no longer creates a session (see
    services/auth_service.py), so this bypasses actually sending/reading a
    verification email by flipping is_email_verified directly in the test
    database — an ad-hoc engine, not the `test_sessionmaker` fixture, so
    every one of this helper's call sites keeps working unchanged — then
    logs in for real, same trick as conftest.py's `client` fixture uses
    for its own default user."""
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.user import User
    from tests.conftest import TEST_DB_NAME, _url

    await client.post("/auth/register", json={"email": email, "password": password})

    engine = create_async_engine(_url(TEST_DB_NAME))
    try:
        async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
            await session.execute(update(User).where(User.email == email).values(is_email_verified=True))
            await session.commit()
    finally:
        await engine.dispose()

    resp = await client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()


def auth_headers(token: str) -> dict:
    """Pass as `headers=auth_headers(token)` on one httpx call to act as a
    different user than the client fixture's default, for that call only."""
    return {"Authorization": f"Bearer {token}"}


async def promote_current_user_to_admin(test_sessionmaker) -> None:
    """Promotes the `client` fixture's auto-registered default test user
    to admin, for tests against admin-gated routes that don't care about
    testing the gate itself — just need to get past it. Assumes the
    `client` fixture's default registration email (see conftest.py's
    `client` fixture — currently "test@example.com")."""
    from sqlalchemy import update

    from app.models.user import User

    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "test@example.com").values(is_admin=True))
        await session.commit()
