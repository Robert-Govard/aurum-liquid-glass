"""Advice: curated, non-urgent financial notes — basic correctness (no
prior test file existed) plus per-user isolation."""
from httpx import AsyncClient

from tests.helpers import auth_headers, register_user, txn_payload as _txn


async def test_rising_category_advice_is_scoped_to_the_caller(client: AsyncClient, account_id, categories):
    """A category that's risen sharply for user B must never appear in
    user A's advice feed."""
    b_tokens = await register_user(client, "adviceb@example.com")
    b_account = (
        await client.post("/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
                          headers=auth_headers(b_tokens["access_token"]))
    ).json()
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")
    from datetime import date
    today = date.today()
    await client.post(
        "/transactions",
        json=_txn(b_account["id"], amount="1000.00", category_id=b_groceries, date=today.isoformat()),
        headers=auth_headers(b_tokens["access_token"]),
    )

    resp = await client.get("/advice")
    assert resp.status_code == 200
    assert all(item["key"] != "rising_category" for item in resp.json()["items"])


async def test_unbudgeted_top_category_advice_is_scoped_to_the_caller(client: AsyncClient, account_id, categories):
    b_tokens = await register_user(client, "adviceb2@example.com")
    b_account = (
        await client.post("/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
                          headers=auth_headers(b_tokens["access_token"]))
    ).json()
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")
    from datetime import date
    today = date.today()
    await client.post(
        "/transactions",
        json=_txn(b_account["id"], amount="500.00", category_id=b_groceries, date=today.isoformat()),
        headers=auth_headers(b_tokens["access_token"]),
    )

    resp = await client.get("/advice")
    assert resp.status_code == 200
    unbudgeted = [item for item in resp.json()["items"] if item["key"] == "unbudgeted_top_category"]
    assert all(item["params"]["category"] != "Groceries" for item in unbudgeted)
