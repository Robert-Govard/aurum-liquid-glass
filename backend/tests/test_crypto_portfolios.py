"""Crypto portfolios: CRUD, plus per-user isolation."""
from tests.helpers import auth_headers, register_user


async def test_create_and_list_portfolio(client):
    resp = await client.post("/crypto/portfolios", json={"name": "Long-term"})
    assert resp.status_code == 201
    listed = await client.get("/crypto/portfolios")
    assert [p["name"] for p in listed.json()] == ["Long-term"]


async def test_user_a_cannot_see_user_bs_portfolio(client):
    b_tokens = await register_user(client, "portb@example.com")
    await client.post("/crypto/portfolios", json={"name": "B's"}, headers=auth_headers(b_tokens["access_token"]))

    a_portfolios = (await client.get("/crypto/portfolios")).json()
    assert a_portfolios == []


async def test_user_a_cannot_update_or_delete_user_bs_portfolio(client):
    b_tokens = await register_user(client, "portb2@example.com")
    b_portfolio = (
        await client.post("/crypto/portfolios", json={"name": "B's"}, headers=auth_headers(b_tokens["access_token"]))
    ).json()

    assert (await client.patch(f"/crypto/portfolios/{b_portfolio['id']}", json={"name": "Hijacked"})).status_code == 404
    assert (await client.delete(f"/crypto/portfolios/{b_portfolio['id']}")).status_code == 404
