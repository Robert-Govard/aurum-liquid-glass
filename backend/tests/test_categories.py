"""Category subcategories (parent_id): creation rules and the one-level-deep
invariant enforced in api/routes/categories.py. Also default-category
deletion: a seeded category can be removed once nothing references it, but
never while it still has transactions.
"""
from httpx import AsyncClient

from app.services.plan_service import FREE_CUSTOM_CATEGORY_LIMIT
from tests.helpers import auth_headers, register_user
from tests.helpers import txn_payload as _txn


async def test_create_subcategory_under_top_level_category(client: AsyncClient, categories):
    groceries = categories["Groceries"]["id"]
    resp = await client.post(
        "/categories", json={"name": "Alcohol", "kind": "expense", "color": "#e34948", "parent_id": groceries}
    )
    assert resp.status_code == 201
    assert resp.json()["parent_id"] == groceries


async def test_subcategory_cannot_have_a_different_kind_than_its_parent(client: AsyncClient, categories):
    groceries = categories["Groceries"]["id"]
    resp = await client.post(
        "/categories", json={"name": "Bad", "kind": "income", "color": "#e34948", "parent_id": groceries}
    )
    assert resp.status_code == 400


async def test_subcategories_are_only_one_level_deep(client: AsyncClient, categories):
    groceries = categories["Groceries"]["id"]
    child = await client.post(
        "/categories", json={"name": "Alcohol", "kind": "expense", "color": "#e34948", "parent_id": groceries}
    )
    child_id = child.json()["id"]

    resp = await client.post(
        "/categories", json={"name": "Wine", "kind": "expense", "color": "#e34948", "parent_id": child_id}
    )
    assert resp.status_code == 400


async def test_category_cannot_be_its_own_parent(client: AsyncClient, categories):
    groceries = categories["Groceries"]["id"]
    resp = await client.patch(f"/categories/{groceries}", json={"parent_id": groceries})
    assert resp.status_code == 400


async def test_a_category_with_subcategories_cannot_itself_become_a_subcategory(client: AsyncClient, categories):
    groceries = categories["Groceries"]["id"]
    dining = categories["Dining Out"]["id"]
    await client.post(
        "/categories", json={"name": "Alcohol", "kind": "expense", "color": "#e34948", "parent_id": groceries}
    )

    resp = await client.patch(f"/categories/{groceries}", json={"parent_id": dining})
    assert resp.status_code == 400


async def test_deleting_a_parent_leaves_children_as_top_level(client: AsyncClient, categories):
    # A default category with transactions can't be deleted (separate rule,
    # tested below) — use a fresh, non-default parent so this test isolates
    # the parent/child rule.
    parent = await client.post("/categories", json={"name": "Custom Parent", "kind": "expense", "color": "#e34948"})
    parent_id = parent.json()["id"]
    created = await client.post(
        "/categories", json={"name": "Alcohol", "kind": "expense", "color": "#e34948", "parent_id": parent_id}
    )
    child_id = created.json()["id"]

    resp = await client.delete(f"/categories/{parent_id}")
    assert resp.status_code == 204

    refetched = await client.get("/categories")
    child = next(c for c in refetched.json() if c["id"] == child_id)
    assert child["parent_id"] is None


async def test_default_category_with_no_transactions_can_be_deleted(client: AsyncClient, categories):
    groceries = categories["Groceries"]["id"]
    assert categories["Groceries"]["is_default"] is True

    resp = await client.delete(f"/categories/{groceries}")
    assert resp.status_code == 204

    refetched = await client.get("/categories")
    assert groceries not in [c["id"] for c in refetched.json()]


async def test_default_category_with_a_transaction_cannot_be_deleted(client: AsyncClient, account_id, categories):
    groceries = categories["Groceries"]["id"]
    await client.post("/transactions", json=_txn(account_id, category_id=groceries))

    resp = await client.delete(f"/categories/{groceries}")
    assert resp.status_code == 400

    refetched = await client.get("/categories")
    assert groceries in [c["id"] for c in refetched.json()]


async def test_default_category_used_only_by_a_split_line_cannot_be_deleted(client: AsyncClient, account_id, categories):
    groceries = categories["Groceries"]["id"]
    sweets = (
        await client.post(
            "/categories", json={"name": "Sweets", "kind": "expense", "color": "#7a869a", "parent_id": groceries}
        )
    ).json()["id"]
    await client.post(
        "/transactions",
        json=_txn(
            account_id,
            amount="100.00",
            category_id=None,
            splits=[
                {"category_id": groceries, "amount": "70.00"},
                {"category_id": sweets, "amount": "30.00"},
            ],
        ),
    )

    resp = await client.delete(f"/categories/{groceries}")
    assert resp.status_code == 400


async def test_default_category_becomes_deletable_once_its_transaction_is_removed(
    client: AsyncClient, account_id, categories
):
    groceries = categories["Groceries"]["id"]
    created = await client.post("/transactions", json=_txn(account_id, category_id=groceries))
    txn_id = created.json()["id"]

    blocked = await client.delete(f"/categories/{groceries}")
    assert blocked.status_code == 400

    assert (await client.delete(f"/transactions/{txn_id}")).status_code == 204

    resp = await client.delete(f"/categories/{groceries}")
    assert resp.status_code == 204


async def test_user_a_cannot_see_user_bs_custom_category(client):
    b_tokens = await register_user(client, "catb@example.com")
    b_category = (
        await client.post(
            "/categories",
            json={"name": "B's Category", "kind": "expense", "color": "#e34948"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    a_categories = (await client.get("/categories")).json()
    assert all(c["id"] != b_category["id"] for c in a_categories)


async def test_user_a_cannot_update_user_bs_category(client):
    b_tokens = await register_user(client, "catb2@example.com")
    b_category = (
        await client.post(
            "/categories",
            json={"name": "B's Category", "kind": "expense", "color": "#e34948"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    resp = await client.patch(f"/categories/{b_category['id']}", json={"name": "Hijacked"})
    assert resp.status_code == 404


async def test_user_a_cannot_delete_user_bs_category(client):
    b_tokens = await register_user(client, "catb3@example.com")
    b_category = (
        await client.post(
            "/categories",
            json={"name": "B's Category", "kind": "expense", "color": "#e34948"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    resp = await client.delete(f"/categories/{b_category['id']}")
    assert resp.status_code == 404


async def test_user_a_cannot_nest_under_user_bs_category(client):
    """A's new subcategory must not be allowed to point parent_id at a
    category A doesn't own — that would leak the fact that the id exists
    (or worse, actually attach to it) if _validate_parent used a bare
    session.get instead of an owner-scoped lookup."""
    b_tokens = await register_user(client, "catb4@example.com")
    b_category = (
        await client.post(
            "/categories",
            json={"name": "B's Category", "kind": "expense", "color": "#e34948"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    resp = await client.post(
        "/categories", json={"name": "Sneaky", "kind": "expense", "color": "#e34948", "parent_id": b_category["id"]}
    )
    assert resp.status_code == 400


async def test_free_user_cannot_exceed_the_custom_category_limit(client):
    for i in range(FREE_CUSTOM_CATEGORY_LIMIT):
        resp = await client.post("/categories", json={"name": f"Custom {i}", "kind": "expense", "color": "#e34948"})
        assert resp.status_code == 201

    over_limit = await client.post(
        "/categories", json={"name": "One too many", "kind": "expense", "color": "#e34948"}
    )
    assert over_limit.status_code == 402
