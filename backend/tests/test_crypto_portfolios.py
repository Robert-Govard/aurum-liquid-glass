"""Crypto portfolios: CRUD, plus per-user isolation."""
import pytest
from sqlalchemy import update

from app.models.user import User
from tests.helpers import auth_headers, register_user


@pytest.fixture(autouse=True)
async def _default_user_is_premium(request, client, test_sessionmaker):
    """This whole file exercises the Premium-gated crypto router (see
    plan_service.py / deps.get_premium_user) — the client fixture's
    default user is Free by design (Task 2's limit tests need that), so
    promote it here for every test except the ones that specifically
    want the Free/402 case (marked @pytest.mark.free_tier), same pattern
    as test_crypto.py/test_advice.py.

    Depends on `client` (even though it's unused directly) purely to force
    fixture ordering — autouse fixtures otherwise instantiate before the
    other fixtures a test requests, which here would run this UPDATE
    before `client` has even registered the "test@example.com" row it's
    meant to promote.
    """
    if "free_tier" in request.keywords:
        return
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "test@example.com").values(is_admin=True))
        await session.commit()


async def test_create_and_list_portfolio(client):
    resp = await client.post("/crypto/portfolios", json={"name": "Long-term"})
    assert resp.status_code == 201
    listed = await client.get("/crypto/portfolios")
    assert [p["name"] for p in listed.json()] == ["Long-term"]


async def test_user_a_cannot_see_user_bs_portfolio(client, test_sessionmaker):
    b_tokens = await register_user(client, "portb@example.com")
    # B is also exercising the Premium-gated crypto router here, so B needs
    # promoting too — see the autouse fixture above for the default user.
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "portb@example.com").values(is_admin=True))
        await session.commit()
    await client.post("/crypto/portfolios", json={"name": "B's"}, headers=auth_headers(b_tokens["access_token"]))

    a_portfolios = (await client.get("/crypto/portfolios")).json()
    assert a_portfolios == []


async def test_user_a_cannot_update_or_delete_user_bs_portfolio(client, test_sessionmaker):
    b_tokens = await register_user(client, "portb2@example.com")
    # Promote B too — see the matching comment in
    # test_user_a_cannot_see_user_bs_portfolio above.
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "portb2@example.com").values(is_admin=True))
        await session.commit()
    b_portfolio = (
        await client.post("/crypto/portfolios", json={"name": "B's"}, headers=auth_headers(b_tokens["access_token"]))
    ).json()

    assert (await client.patch(f"/crypto/portfolios/{b_portfolio['id']}", json={"name": "Hijacked"})).status_code == 404
    assert (await client.delete(f"/crypto/portfolios/{b_portfolio['id']}")).status_code == 404
