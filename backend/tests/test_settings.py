"""App settings: one row per user (currency, alert thresholds), plus
per-user isolation."""
from tests.helpers import auth_headers, register_user


async def test_get_settings_returns_the_seeded_defaults(client):
    resp = await client.get("/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "USD"


async def test_update_settings_persists_a_partial_change(client):
    resp = await client.patch("/settings", json={"currency": "EUR"})
    assert resp.status_code == 200
    assert resp.json()["currency"] == "EUR"

    refetched = await client.get("/settings")
    assert refetched.json()["currency"] == "EUR"


async def test_user_a_changing_currency_does_not_affect_user_b(client):
    b_tokens = await register_user(client, "setb@example.com")

    await client.patch("/settings", json={"currency": "EUR"})

    b_settings = await client.get("/settings", headers=auth_headers(b_tokens["access_token"]))
    assert b_settings.json()["currency"] == "USD"
