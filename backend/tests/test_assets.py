"""Manually-tracked assets: CRUD, valuation history, plus per-user isolation."""
from tests.helpers import auth_headers, register_user


def _payload(**overrides) -> dict:
    payload = {
        "name": "Vacation House",
        "asset_class": "real_estate",
        "value": "250000.00",
    }
    payload.update(overrides)
    return payload


async def test_create_and_list_asset(client):
    resp = await client.post("/assets", json=_payload())
    assert resp.status_code == 201
    listed = await client.get("/assets")
    assert [a["name"] for a in listed.json()] == ["Vacation House"]


async def test_add_and_list_valuations(client):
    created = (await client.post("/assets", json=_payload())).json()
    await client.post(f"/assets/{created['id']}/valuations", json={"value": "260000.00", "as_of_date": "2026-02-01"})
    valuations = (await client.get(f"/assets/{created['id']}/valuations")).json()
    assert len(valuations) == 2  # the create-time valuation plus this one


async def test_user_a_cannot_see_user_bs_asset(client):
    b_tokens = await register_user(client, "assetb@example.com")
    await client.post("/assets", json=_payload(name="B's House"), headers=auth_headers(b_tokens["access_token"]))

    a_assets = (await client.get("/assets")).json()
    assert a_assets == []


async def test_user_a_cannot_update_or_delete_user_bs_asset(client):
    b_tokens = await register_user(client, "assetb2@example.com")
    b_asset = (
        await client.post("/assets", json=_payload(name="B's House"), headers=auth_headers(b_tokens["access_token"]))
    ).json()

    assert (await client.patch(f"/assets/{b_asset['id']}", json={"name": "Hijacked"})).status_code == 404
    assert (await client.delete(f"/assets/{b_asset['id']}")).status_code == 404


async def test_user_a_cannot_add_or_list_valuations_on_user_bs_asset(client):
    b_tokens = await register_user(client, "assetb3@example.com")
    b_asset = (
        await client.post("/assets", json=_payload(name="B's House"), headers=auth_headers(b_tokens["access_token"]))
    ).json()

    add_resp = await client.post(f"/assets/{b_asset['id']}/valuations", json={"value": "1.00", "as_of_date": "2026-02-01"})
    assert add_resp.status_code == 404

    list_resp = await client.get(f"/assets/{b_asset['id']}/valuations")
    assert list_resp.status_code == 404
