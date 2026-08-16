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
