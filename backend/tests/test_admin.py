"""Admin: list/disable/delete users, gated behind is_admin."""
from decimal import Decimal

from sqlalchemy import update

from app.models.user import User


async def _register(client, email: str) -> dict:
    resp = await client.post("/auth/register", json={"email": email, "password": "hunter22"})
    return resp.json()


async def _make_admin(test_sessionmaker, email: str) -> None:
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == email).values(is_admin=True))
        await session.commit()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_non_admin_gets_403(client):
    tokens = await _register(client, "plain@example.com")
    resp = await client.get("/admin/users", headers=_auth(tokens["access_token"]))
    assert resp.status_code == 403


async def test_missing_token_gets_401(client):
    # The `client` fixture now auto-authenticates as its own default test
    # user (see conftest.py), so a genuinely tokenless request has to drop
    # that default Authorization header for this one call.
    del client.headers["Authorization"]
    resp = await client.get("/admin/users")
    assert resp.status_code == 401


async def test_admin_can_list_users(client, test_sessionmaker):
    admin_tokens = await _register(client, "admin@example.com")
    await _make_admin(test_sessionmaker, "admin@example.com")
    await _register(client, "other@example.com")

    resp = await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    # The `client` fixture auto-registers its own default user
    # ("test@example.com") before this test runs any of its own
    # registrations, so it shows up here too — assert the two users this
    # test actually cares about are present rather than pinning the total.
    assert {"admin@example.com", "other@example.com"} <= emails
    # never leaks the hash
    assert all("password" not in u for u in resp.json())


async def test_admin_can_disable_a_user(client, test_sessionmaker):
    admin_tokens = await _register(client, "admin2@example.com")
    await _make_admin(test_sessionmaker, "admin2@example.com")
    target_tokens = await _register(client, "target@example.com")

    users = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    target_id = next(u["id"] for u in users if u["email"] == "target@example.com")

    patch_resp = await client.patch(
        f"/admin/users/{target_id}", json={"is_active": False}, headers=_auth(admin_tokens["access_token"])
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    # the disabled user's existing refresh token stops working
    refresh_resp = await client.post("/auth/refresh", json={"refresh_token": target_tokens["refresh_token"]})
    assert refresh_resp.status_code == 401
    login_resp = await client.post("/auth/login", json={"email": "target@example.com", "password": "hunter22"})
    assert login_resp.status_code == 401


async def test_admin_can_delete_a_user(client, test_sessionmaker):
    admin_tokens = await _register(client, "admin3@example.com")
    await _make_admin(test_sessionmaker, "admin3@example.com")
    await _register(client, "todelete@example.com")

    users = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    target_id = next(u["id"] for u in users if u["email"] == "todelete@example.com")

    delete_resp = await client.delete(f"/admin/users/{target_id}", headers=_auth(admin_tokens["access_token"]))
    assert delete_resp.status_code == 204

    remaining = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    assert all(u["id"] != target_id for u in remaining)


async def test_admin_cannot_disable_own_account(client, test_sessionmaker):
    admin_tokens = await _register(client, "selflock1@example.com")
    await _make_admin(test_sessionmaker, "selflock1@example.com")

    users = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    own_id = next(u["id"] for u in users if u["email"] == "selflock1@example.com")

    resp = await client.patch(
        f"/admin/users/{own_id}", json={"is_active": False}, headers=_auth(admin_tokens["access_token"])
    )
    assert resp.status_code == 400


async def test_admin_cannot_delete_own_account(client, test_sessionmaker):
    admin_tokens = await _register(client, "selflock2@example.com")
    await _make_admin(test_sessionmaker, "selflock2@example.com")

    users = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    own_id = next(u["id"] for u in users if u["email"] == "selflock2@example.com")

    resp = await client.delete(f"/admin/users/{own_id}", headers=_auth(admin_tokens["access_token"]))
    assert resp.status_code == 400


async def test_admin_list_includes_per_user_stats(client, test_sessionmaker):
    admin_tokens = await _register(client, "statsadmin@example.com")
    await _make_admin(test_sessionmaker, "statsadmin@example.com")

    target_tokens = await _register(client, "statstarget@example.com")
    target_account = (
        await client.post(
            "/accounts",
            json={"name": "Target Wallet", "type": "checking", "currency": "USD"},
            headers=_auth(target_tokens["access_token"]),
        )
    ).json()
    target_categories = (await client.get("/categories", headers=_auth(target_tokens["access_token"]))).json()
    salary_id = next(c["id"] for c in target_categories if c["name"] == "Salary")
    await client.post(
        "/transactions",
        json={
            "account_id": target_account["id"],
            "type": "income",
            "amount": "500.00",
            "description": "salary",
            "date": "2026-01-15",
            "category_id": salary_id,
        },
        headers=_auth(target_tokens["access_token"]),
    )

    users = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    target = next(u for u in users if u["email"] == "statstarget@example.com")
    assert target["accounts_count"] == 1
    assert target["transactions_count"] == 1
    assert Decimal(str(target["net_worth"])) == Decimal("500.00")

    # A user with zero accounts/transactions/assets still gets zeroed
    # stats, not a missing key or a crash — and critically, does NOT show
    # statstarget's 500.00 (the thing a batched cross-user query could get
    # wrong: mixing sums between users).
    admin_self = next(u for u in users if u["email"] == "statsadmin@example.com")
    assert admin_self["accounts_count"] == 0
    assert admin_self["transactions_count"] == 0
    assert Decimal(str(admin_self["net_worth"])) == Decimal("0")
