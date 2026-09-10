"""Net worth: cash + assets aggregated into one trend line and a
class/role/risk breakdown — basic correctness (no prior test file existed)
plus per-user isolation."""
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import auth_headers, money, register_user, txn_payload as _txn


async def test_net_worth_reflects_cash_and_assets(client: AsyncClient, account_id, categories):
    await client.post(
        "/transactions",
        json=_txn(account_id, type="income", amount="1000.00", category_id=categories["Salary"]["id"], date="2026-08-01"),
    )
    await client.post(
        "/assets",
        json={"name": "House", "asset_class": "real_estate", "value": "200000.00", "as_of_date": "2026-08-01"},
    )

    resp = await client.get("/net-worth/summary", params={"range": "30d"})
    body = resp.json()
    assert money(body["current"]) == Decimal("201000.00")

    breakdown = {row["key"]: row for row in body["breakdown"]}
    assert money(breakdown["cash"]["amount"]) == Decimal("1000.00")
    assert money(breakdown["real_estate"]["amount"]) == Decimal("200000.00")


async def test_net_worth_excludes_another_users_accounts_transactions_and_assets(client: AsyncClient, account_id, categories):
    b_tokens = await register_user(client, "networthb@example.com")
    b_account = (
        await client.post("/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
                          headers=auth_headers(b_tokens["access_token"]))
    ).json()
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_salary = next(c["id"] for c in b_categories if c["name"] == "Salary")
    await client.post(
        "/transactions",
        json=_txn(b_account["id"], type="income", amount="9999.00", category_id=b_salary, date="2026-08-01"),
        headers=auth_headers(b_tokens["access_token"]),
    )
    await client.post(
        "/assets",
        json={"name": "B's House", "asset_class": "real_estate", "value": "999999.00", "as_of_date": "2026-08-01"},
        headers=auth_headers(b_tokens["access_token"]),
    )

    await client.post(
        "/transactions",
        json=_txn(account_id, type="income", amount="500.00", category_id=categories["Salary"]["id"], date="2026-08-01"),
    )

    resp = await client.get("/net-worth/summary", params={"range": "30d"})
    assert money(resp.json()["current"]) == Decimal("500.00")


async def test_capital_role_and_risk_level_summaries_exclude_another_users_assets(client: AsyncClient):
    b_tokens = await register_user(client, "networthb2@example.com")
    await client.post(
        "/assets",
        json={"name": "B's Crypto", "asset_class": "crypto", "value": "50000.00", "as_of_date": "2026-08-01",
              "risk_level": "high", "capital_role": "drain"},
        headers=auth_headers(b_tokens["access_token"]),
    )

    await client.post(
        "/assets",
        json={"name": "My Bond", "asset_class": "other", "value": "1000.00", "as_of_date": "2026-08-01",
              "risk_level": "low", "capital_role": "income"},
    )

    resp = await client.get("/net-worth/summary", params={"range": "30d"})
    body = resp.json()

    drain_role = next(r for r in body["capital_roles"] if r["role"] == "drain")
    assert money(drain_role["total_value"]) == Decimal("0")  # B's asset must not count here
    # total_value alone doesn't discriminate _capital_role_summary's own
    # scoping: it's derived from current_by_asset, which is populated by a
    # SEPARATE, already-scoped query — so total_value would stay 0 even if
    # _capital_role_summary's own `roles_result` query leaked B's asset in
    # (its value just wouldn't be found in current_by_asset). `count`
    # increments unconditionally per row from that same roles_result query,
    # so it's the field that actually catches an unscoped read there.
    assert drain_role["count"] == 0  # B's asset must not be counted here either

    high_risk = next(r for r in body["risk_levels"] if r["risk_level"] == "high")
    assert money(high_risk["total_value"]) == Decimal("0")  # B's asset must not count here
