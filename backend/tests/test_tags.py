"""Tags: CRUD, case-insensitive dedup on create, and their use on
transactions (create/update with tag_ids, filtering by tag_id).
"""
from httpx import AsyncClient

from tests.helpers import auth_headers, register_user
from tests.helpers import txn_payload as _txn


async def test_create_tag(client: AsyncClient):
    resp = await client.post("/tags", json={"name": "Georgia Trip"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "Georgia Trip"


async def test_create_tag_dedups_case_insensitively(client: AsyncClient):
    first = await client.post("/tags", json={"name": "Tax Deductible"})
    second = await client.post("/tags", json={"name": "tax deductible"})

    assert first.json()["id"] == second.json()["id"]
    assert len((await client.get("/tags")).json()) == 1


async def test_delete_tag(client: AsyncClient):
    created = await client.post("/tags", json={"name": "Temp"})
    resp = await client.delete(f"/tags/{created.json()['id']}")
    assert resp.status_code == 204
    assert (await client.get("/tags")).json() == []


async def test_create_transaction_with_tags(client: AsyncClient, account_id, categories):
    tag = await client.post("/tags", json={"name": "Georgia"})
    tag_id = tag.json()["id"]

    resp = await client.post(
        "/transactions",
        json=_txn(account_id, category_id=categories["Groceries"]["id"], tag_ids=[tag_id]),
    )
    assert resp.status_code == 201
    assert [t["id"] for t in resp.json()["tags"]] == [tag_id]


async def test_update_transaction_replaces_tags(client: AsyncClient, account_id, categories):
    tag_a = (await client.post("/tags", json={"name": "A"})).json()["id"]
    tag_b = (await client.post("/tags", json={"name": "B"})).json()["id"]
    created = await client.post(
        "/transactions", json=_txn(account_id, category_id=categories["Groceries"]["id"], tag_ids=[tag_a])
    )
    txn_id = created.json()["id"]

    resp = await client.patch(f"/transactions/{txn_id}", json={"tag_ids": [tag_b]})
    assert [t["id"] for t in resp.json()["tags"]] == [tag_b]

    # Omitting tag_ids entirely leaves the existing tags untouched.
    resp = await client.patch(f"/transactions/{txn_id}", json={"description": "renamed"})
    assert [t["id"] for t in resp.json()["tags"]] == [tag_b]

    # Sending an empty list clears them.
    resp = await client.patch(f"/transactions/{txn_id}", json={"tag_ids": []})
    assert resp.json()["tags"] == []


async def test_create_transaction_rejects_unknown_tag_id(client: AsyncClient, account_id, categories):
    resp = await client.post(
        "/transactions",
        json=_txn(account_id, category_id=categories["Groceries"]["id"], tag_ids=[999999]),
    )
    assert resp.status_code == 400


async def test_filter_transactions_by_tag(client: AsyncClient, account_id, categories):
    tag = (await client.post("/tags", json={"name": "Filtered"})).json()["id"]
    await client.post(
        "/transactions", json=_txn(account_id, category_id=categories["Groceries"]["id"], tag_ids=[tag])
    )
    await client.post("/transactions", json=_txn(account_id, category_id=categories["Groceries"]["id"]))

    resp = await client.get("/transactions", params={"tag_id": tag})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["tags"][0]["id"] == tag


async def test_user_a_cannot_see_user_bs_tags(client):
    b_tokens = await register_user(client, "tagb@example.com")
    await client.post("/tags", json={"name": "b-only"}, headers=auth_headers(b_tokens["access_token"]))

    a_tags = (await client.get("/tags")).json()
    assert all(t["name"] != "b-only" for t in a_tags)


async def test_user_a_and_b_can_each_have_a_tag_with_the_same_name(client):
    """Tag names are unique per-user now, not globally — two different
    users independently creating "groceries" must not collide."""
    b_tokens = await register_user(client, "tagb2@example.com")

    a_tag = (await client.post("/tags", json={"name": "groceries"})).json()
    b_tag = (
        await client.post("/tags", json={"name": "groceries"}, headers=auth_headers(b_tokens["access_token"]))
    ).json()

    assert a_tag["id"] != b_tag["id"]
    assert a_tag["name"] == b_tag["name"] == "groceries"


async def test_user_a_cannot_delete_user_bs_tag(client):
    b_tokens = await register_user(client, "tagb3@example.com")
    b_tag = (
        await client.post("/tags", json={"name": "b-only"}, headers=auth_headers(b_tokens["access_token"]))
    ).json()

    resp = await client.delete(f"/tags/{b_tag['id']}")
    assert resp.status_code == 404
