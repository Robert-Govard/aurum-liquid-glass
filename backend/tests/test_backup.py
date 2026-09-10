"""Full-database backup export/import (services/backup_service.py) — only
the parts this change touched: subcategories (self-referential parent_id)
and tags (many-to-many) surviving a round trip.
"""
from httpx import AsyncClient

from tests.helpers import txn_payload as _txn


async def test_backup_roundtrip_preserves_subcategories_and_tags(client: AsyncClient, account_id, categories):
    parent = await client.post("/categories", json={"name": "Custom Parent", "kind": "expense", "color": "#e34948"})
    parent_id = parent.json()["id"]
    child = await client.post(
        "/categories", json={"name": "Custom Child", "kind": "expense", "color": "#e34948", "parent_id": parent_id}
    )
    child_id = child.json()["id"]

    tag = (await client.post("/tags", json={"name": "Roundtrip"})).json()["id"]
    created = await client.post("/transactions", json=_txn(account_id, category_id=child_id, tag_ids=[tag]))
    txn_id = created.json()["id"]

    export_resp = await client.get("/backup/export")
    assert export_resp.status_code == 200
    payload = export_resp.json()

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    refetched_categories = {c["id"]: c for c in (await client.get("/categories")).json()}
    assert refetched_categories[child_id]["parent_id"] == parent_id

    refetched_txn = next(t for t in (await client.get("/transactions")).json()["items"] if t["id"] == txn_id)
    assert [t["id"] for t in refetched_txn["tags"]] == [tag]


async def test_backup_import_rejects_transaction_with_unknown_tag_id(client: AsyncClient, account_id, categories):
    export_resp = await client.get("/backup/export")
    payload = export_resp.json()

    created = await client.post(
        "/transactions", json=_txn(account_id, category_id=categories["Groceries"]["id"], date="2026-01-01")
    )
    payload["transactions"] = (await client.get("/transactions")).json()["items"]
    # Reshape to the backup wire format (flat FKs, not nested account/category
    # objects) and inject a tag_id that doesn't exist in payload["tags"].
    payload["transactions"] = [
        {
            "id": t["id"],
            "account_id": t["account_id"],
            "category_id": t["category_id"],
            "transfer_account_id": t["transfer_account_id"],
            "type": t["type"],
            "amount": t["amount"],
            "description": t["description"],
            "merchant": t["merchant"],
            "notes": t["notes"],
            "date": t["date"],
            "tag_ids": [999999] if t["id"] == created.json()["id"] else [],
        }
        for t in payload["transactions"]
    ]

    resp = await client.post("/backup/import", json=payload)
    assert resp.status_code == 400


async def test_backup_roundtrip_preserves_transaction_splits(client: AsyncClient, account_id, categories):
    groceries = categories["Groceries"]["id"]
    sweets = (
        await client.post("/categories", json={"name": "Sweets", "kind": "expense", "color": "#7a869a", "parent_id": groceries})
    ).json()["id"]
    created = await client.post(
        "/transactions",
        json=_txn(
            account_id,
            amount="100.00",
            category_id=None,
            splits=[
                {"category_id": groceries, "amount": "70.00"},
                {"category_id": sweets, "amount": "30.00", "note": "candy and snacks"},
            ],
        ),
    )
    txn_id = created.json()["id"]

    payload = (await client.get("/backup/export")).json()
    assert len(payload["transaction_splits"]) == 2

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    refetched = next(t for t in (await client.get("/transactions")).json()["items"] if t["id"] == txn_id)
    splits_by_note = {s["note"]: s for s in refetched["splits"]}
    assert splits_by_note["candy and snacks"]["category_id"] == sweets
    assert refetched["category"] is None


async def test_export_only_includes_the_callers_own_data(client: AsyncClient, account_id, categories):
    from tests.helpers import auth_headers, register_user

    b_tokens = await register_user(client, "backupb@example.com")
    await client.post(
        "/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
        headers=auth_headers(b_tokens["access_token"]),
    )

    payload = (await client.get("/backup/export")).json()
    account_names = {a["name"] for a in payload["accounts"]}
    assert "B Wallet" not in account_names


async def test_import_never_touches_another_users_data(client: AsyncClient, account_id, categories):
    """The single most important property of self-service restore: importing
    a backup must only ever affect the calling user's own rows."""
    from tests.helpers import auth_headers, register_user

    b_tokens = await register_user(client, "backupb2@example.com")
    b_account_resp = await client.post(
        "/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
        headers=auth_headers(b_tokens["access_token"]),
    )
    b_account_id = b_account_resp.json()["id"]

    payload = (await client.get("/backup/export")).json()
    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    b_accounts = (await client.get("/accounts", headers=auth_headers(b_tokens["access_token"]))).json()
    assert any(a["id"] == b_account_id for a in b_accounts)


async def test_import_does_not_break_sequence_for_other_users(client: AsyncClient, account_id, categories):
    """Regression guard for the sequence-reset bug this task fixes: restoring
    a user's own OLD, low-numbered backup must never roll the shared id
    sequence backward below ids another user's rows already occupy — doing
    so would make a future ordinary INSERT by that other user collide with
    their own existing row."""
    from tests.helpers import auth_headers, register_user

    payload = (await client.get("/backup/export")).json()  # A's own backup, low ids

    b_tokens = await register_user(client, "backupb3@example.com")
    b_headers = auth_headers(b_tokens["access_token"])
    # Push the shared accounts-table sequence well past A's own ids.
    for i in range(5):
        resp = await client.post(
            "/accounts", json={"name": f"B Account {i}", "type": "cash", "currency": "USD"}, headers=b_headers
        )
        assert resp.status_code == 201

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    # If the sequence were wrongly rolled back to A's own (lower) backup
    # max, this next INSERT would collide with one of B's 5 accounts above
    # and 500 instead of 201.
    new_b_account = await client.post(
        "/accounts", json={"name": "B Account After Restore", "type": "cash", "currency": "USD"}, headers=b_headers
    )
    assert new_b_account.status_code == 201
    b_accounts = (await client.get("/accounts", headers=b_headers)).json()
    assert len({a["id"] for a in b_accounts}) == len(b_accounts)  # no duplicate ids
