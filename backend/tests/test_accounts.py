"""Accounts: CRUD plus per-user isolation (no test file existed for this
router before — it was only ever exercised indirectly via other tests'
`account_id` fixture)."""
from app.services.plan_service import FREE_ACCOUNT_LIMIT
from sqlalchemy import update

from app.models.user import User
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


async def test_free_user_cannot_exceed_the_account_limit(client):
    # Every test starts against a freshly truncated database (see
    # conftest.py's autouse _clean_database fixture) — this user has zero
    # accounts at the start of this test regardless of what other tests do.
    for i in range(FREE_ACCOUNT_LIMIT):
        resp = await client.post("/accounts", json={"name": f"Account {i}", "type": "checking", "currency": "USD"})
        assert resp.status_code == 201

    over_limit = await client.post("/accounts", json={"name": "One too many", "type": "checking", "currency": "USD"})
    assert over_limit.status_code == 402


async def test_premium_user_has_no_account_limit(client, test_sessionmaker):
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "test@example.com").values(is_admin=True))
        await session.commit()

    for i in range(FREE_ACCOUNT_LIMIT + 2):
        resp = await client.post("/accounts", json={"name": f"Account {i}", "type": "checking", "currency": "USD"})
        assert resp.status_code == 201
