"""Admin: list/disable/delete users, gated behind is_admin."""
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
    resp = await client.get("/admin/users")
    assert resp.status_code == 401


async def test_admin_can_list_users(client, test_sessionmaker):
    admin_tokens = await _register(client, "admin@example.com")
    await _make_admin(test_sessionmaker, "admin@example.com")
    await _register(client, "other@example.com")

    resp = await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert emails == {"admin@example.com", "other@example.com"}
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
