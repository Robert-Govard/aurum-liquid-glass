"""Budgets: category-kind restriction, one-budget-per-category, and the
spent/remaining/over-budget math behind the Budget page's progress bars.
"""
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import money, txn_payload


async def test_budget_rejects_income_category(client: AsyncClient, categories):
    resp = await client.post(
        "/budgets", json={"category_id": categories["Salary"]["id"], "monthly_limit": "500.00"}
    )
    assert resp.status_code == 400


async def test_budget_rejects_duplicate_category(client: AsyncClient, categories):
    category_id = categories["Groceries"]["id"]
    first = await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "300.00"})
    assert first.status_code == 201

    second = await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "400.00"})
    assert second.status_code == 400


async def test_status_reports_spent_remaining_and_over_budget(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "100.00"})

    for amount in ["60.00", "60.00"]:  # 120.00 total, over a 100.00 limit
        await client.post(
            "/transactions",
            json=txn_payload(account_id, amount=amount, category_id=category_id, date="2026-08-10"),
        )

    resp = await client.get("/budgets/status", params={"year": 2026, "month": 8})
    item = resp.json()["items"][0]
    assert money(item["spent"]) == Decimal("120.00")
    assert money(item["remaining"]) == Decimal("-20.00")
    assert item["percent"] == 120.0
    assert item["is_over_budget"] is True


async def test_status_only_counts_the_selected_month(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "100.00"})
    await client.post(
        "/transactions", json=txn_payload(account_id, amount="90.00", category_id=category_id, date="2026-07-15")
    )

    resp = await client.get("/budgets/status", params={"year": 2026, "month": 8})
    item = resp.json()["items"][0]
    assert money(item["spent"]) == 0
    assert item["is_over_budget"] is False


async def test_status_is_empty_list_when_no_budgets_exist(client: AsyncClient):
    resp = await client.get("/budgets/status", params={"year": 2026, "month": 8})
    assert resp.json()["items"] == []


async def test_update_budget_changes_the_limit(client: AsyncClient, categories):
    category_id = categories["Groceries"]["id"]
    created = await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "100.00"})
    budget_id = created.json()["id"]

    resp = await client.patch(f"/budgets/{budget_id}", json={"monthly_limit": "250.00"})
    assert resp.status_code == 200
    assert money(resp.json()["monthly_limit"]) == Decimal("250.00")


async def test_delete_budget_removes_it_from_status(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    created = await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "100.00"})
    budget_id = created.json()["id"]

    delete_resp = await client.delete(f"/budgets/{budget_id}")
    assert delete_resp.status_code == 204

    status = await client.get("/budgets/status", params={"year": 2026, "month": 8})
    assert status.json()["items"] == []
