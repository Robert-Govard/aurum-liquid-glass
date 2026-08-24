"""Category subcategories (parent_id): creation rules and the one-level-deep
invariant enforced in api/routes/categories.py.
"""
from httpx import AsyncClient


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
    # A default category can't be deleted at all (separate rule) — use a
    # fresh, non-default parent so this test isolates the parent/child rule.
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
