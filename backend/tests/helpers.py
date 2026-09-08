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
    Returns the /auth/register response body (access_token, refresh_token,
    token_type)."""
    resp = await client.post("/auth/register", json={"email": email, "password": password})
    return resp.json()


def auth_headers(token: str) -> dict:
    """Pass as `headers=auth_headers(token)` on one httpx call to act as a
    different user than the client fixture's default, for that call only."""
    return {"Authorization": f"Bearer {token}"}
