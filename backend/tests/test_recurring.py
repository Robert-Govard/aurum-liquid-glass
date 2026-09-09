"""Recurring transaction templates: CRUD, posting, plus per-user isolation."""
from tests.helpers import auth_headers, register_user


def _payload(account_id: int, **overrides) -> dict:
    payload = {
        "account_id": account_id,
        "type": "expense",
        "amount": "9.99",
        "description": "Streaming subscription",
        "frequency": "monthly",
        "anchor_date": "2026-01-01",
    }
    payload.update(overrides)
    return payload


async def test_create_and_list_recurring(client, account_id):
    resp = await client.post("/recurring", json=_payload(account_id))
    assert resp.status_code == 201
    listed = await client.get("/recurring")
    assert len(listed.json()) == 1


async def test_post_recurring_creates_a_transaction(client, account_id):
    created = (await client.post("/recurring", json=_payload(account_id))).json()
    resp = await client.post(f"/recurring/{created['id']}/post")
    assert resp.status_code == 201
    assert resp.json()["last_posted_date"] is not None


async def test_user_a_cannot_see_user_bs_recurring(client, account_id):
    b_tokens = await register_user(client, "recb@example.com")
    b_account = (
        await client.post(
            "/accounts",
            json={"name": "B's", "type": "checking", "currency": "USD"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()
    await client.post("/recurring", json=_payload(b_account["id"]), headers=auth_headers(b_tokens["access_token"]))

    a_list = (await client.get("/recurring")).json()
    assert a_list == []


async def test_user_a_cannot_update_delete_or_post_user_bs_recurring(client):
    b_tokens = await register_user(client, "recb2@example.com")
    b_account = (
        await client.post(
            "/accounts",
            json={"name": "B's", "type": "checking", "currency": "USD"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()
    b_recurring = (
        await client.post(
            "/recurring", json=_payload(b_account["id"]), headers=auth_headers(b_tokens["access_token"])
        )
    ).json()

    assert (await client.patch(f"/recurring/{b_recurring['id']}", json={"amount": "1.00"})).status_code == 404
    assert (await client.post(f"/recurring/{b_recurring['id']}/post")).status_code == 404
    assert (await client.delete(f"/recurring/{b_recurring['id']}")).status_code == 404
