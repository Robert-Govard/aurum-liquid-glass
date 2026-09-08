"""Accounts: CRUD plus per-user isolation (no test file existed for this
router before — it was only ever exercised indirectly via other tests'
`account_id` fixture)."""
from tests.helpers import auth_headers, register_user


async def test_create_and_list_account(client):
    resp = await client.post("/accounts", json={"name": "Checking", "type": "checking", "currency": "USD"})
    assert resp.status_code == 201
    listed = await client.get("/accounts")
    assert [a["name"] for a in listed.json()] == ["Checking"]


async def test_user_a_cannot_see_user_bs_accounts(client):
    a_account = (await client.post("/accounts", json={"name": "A's", "type": "checking", "currency": "USD"})).json()

    b_tokens = await register_user(client, "b@example.com")
    b_account = (
        await client.post(
            "/accounts", json={"name": "B's", "type": "checking", "currency": "USD"}, headers=auth_headers(b_tokens["access_token"])
        )
    ).json()

    a_list = (await client.get("/accounts")).json()
    assert [a["id"] for a in a_list] == [a_account["id"]]

    b_list = (await client.get("/accounts", headers=auth_headers(b_tokens["access_token"]))).json()
    assert [a["id"] for a in b_list] == [b_account["id"]]


async def test_user_a_cannot_update_user_bs_account(client):
    b_tokens = await register_user(client, "b2@example.com")
    b_account = (
        await client.post(
            "/accounts", json={"name": "B's", "type": "checking", "currency": "USD"}, headers=auth_headers(b_tokens["access_token"])
        )
    ).json()

    resp = await client.patch(f"/accounts/{b_account['id']}", json={"name": "Hijacked"})
    assert resp.status_code == 404


async def test_user_a_cannot_delete_user_bs_account(client):
    b_tokens = await register_user(client, "b3@example.com")
    b_account = (
        await client.post(
            "/accounts", json={"name": "B's", "type": "checking", "currency": "USD"}, headers=auth_headers(b_tokens["access_token"])
        )
    ).json()

    resp = await client.delete(f"/accounts/{b_account['id']}")
    assert resp.status_code == 404

    still_there = await client.get("/accounts", headers=auth_headers(b_tokens["access_token"]))
    assert len(still_there.json()) == 1
