"""Full-database backup export/import (services/backup_service.py):
round-trip correctness of subcategories (self-referential parent_id), tags
(many-to-many), and transaction splits; per-user isolation of both export
(a user's export never contains another user's rows) and import (restoring
never reads, modifies, or wipes another user's data, and never corrupts the
shared id sequences other users rely on — including under a concurrent,
not-yet-committed insert); regression guard for sequence monotonicity under
concurrent inserts; and that both endpoints still require authentication.
"""
from httpx import AsyncClient
from sqlalchemy import text

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
    # Guard against a vacuously-passing empty export: the calling user's own
    # account (created by the `account_id` fixture) must actually be present.
    assert account_id in {a["id"] for a in payload["accounts"]}


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


async def test_backup_routes_require_authentication(client: AsyncClient):
    """The admin gate that used to guard /backup/* was replaced with a plain
    authenticated-user gate (see app/api/routes/backup.py) — this pins down
    that "authenticated" is still enforced, not dropped entirely."""
    del client.headers["Authorization"]
    export_resp = await client.get("/backup/export")
    assert export_resp.status_code == 401

    import_resp = await client.post("/backup/import", json={})
    assert import_resp.status_code == 401


async def test_import_resets_sequence_past_uncommitted_concurrent_insert(
    client: AsyncClient, account_id, categories, test_sessionmaker
):
    """Regression test for the _reset_sequence fix: MAX(id) alone only sees
    COMMITTED rows, so a concurrent transaction that already called
    nextval() (reserving an id) but hasn't committed yet could be missed,
    letting `setval` roll the sequence back below a reservation that later
    commits. `_reset_sequence` now also takes pg_sequence_last_value(...)
    into account, which reflects every nextval() call ever made against the
    sequence regardless of commit state.

    This opens a second, independent AsyncSession (via test_sessionmaker,
    same test database as the `client` fixture) and reserves an id on the
    `accounts` sequence directly with nextval() — without inserting a row or
    committing — to simulate a concurrent, in-flight INSERT. A restore is
    then run through the normal HTTP client while that reservation is still
    uncommitted, followed by committing the second session. A subsequent
    ordinary account creation must still get a fresh, non-colliding id.
    """
    payload = (await client.get("/backup/export")).json()

    async with test_sessionmaker() as other_session:
        # Reserves the next id on the accounts sequence (advances its
        # internal counter) without committing — this is the "concurrent
        # uncommitted insert" MAX(id) alone can't see.
        reserved_id = (
            await other_session.execute(text("SELECT nextval(pg_get_serial_sequence('accounts', 'id'))"))
        ).scalar_one()

        # The restore runs while `other_session`'s transaction (holding the
        # reservation above) is still open and uncommitted.
        import_resp = await client.post("/backup/import", json=payload)
        assert import_resp.status_code == 200, import_resp.text

        await other_session.commit()

    # A subsequent ordinary account creation must not collide with the
    # reserved-but-was-uncommitted-during-restore id.
    new_account = await client.post(
        "/accounts", json={"name": "Post-Restore Account", "type": "cash", "currency": "USD"}
    )
    assert new_account.status_code == 201, new_account.text
    assert new_account.json()["id"] != reserved_id
