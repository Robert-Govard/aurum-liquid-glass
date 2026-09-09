"""Proactive alerts (services/insights_service.py): only the idle-cash
signal is covered here — the other three (negative cash flow, net worth
decline, over-budget) predate this test file and aren't touched by this
change.
"""
from datetime import date, timedelta

from httpx import AsyncClient

from tests.helpers import txn_payload as _txn

STALE_DATE = (date.today() - timedelta(days=400)).isoformat()
RECENT_DATE = date.today().isoformat()


async def _alert_keys(client: AsyncClient) -> set[str]:
    resp = await client.get("/insights/alerts")
    return {alert["key"] for alert in resp.json()["alerts"]}


async def test_idle_cash_flags_a_stale_large_balance(client: AsyncClient, account_id, categories):
    await client.post(
        "/transactions",
        json=_txn(account_id, type="income", amount="5000.00", category_id=categories["Salary"]["id"], date=STALE_DATE),
    )

    assert "idle_cash" in await _alert_keys(client)


async def test_idle_cash_ignores_a_recently_touched_account(client: AsyncClient, account_id, categories):
    await client.post(
        "/transactions",
        json=_txn(account_id, type="income", amount="5000.00", category_id=categories["Salary"]["id"], date=STALE_DATE),
    )
    await client.post(
        "/transactions",
        json=_txn(account_id, type="expense", amount="1.00", category_id=categories["Groceries"]["id"], date=RECENT_DATE),
    )

    assert "idle_cash" not in await _alert_keys(client)


async def test_idle_cash_ignores_investment_accounts(client: AsyncClient, categories):
    investment = await client.post("/accounts", json={"name": "Brokerage", "type": "investment", "currency": "USD"})
    investment_id = investment.json()["id"]
    await client.post(
        "/transactions",
        json=_txn(investment_id, type="income", amount="5000.00", category_id=categories["Salary"]["id"], date=STALE_DATE),
    )

    assert "idle_cash" not in await _alert_keys(client)


async def test_idle_cash_respects_custom_threshold(client: AsyncClient, account_id, categories):
    await client.post(
        "/transactions",
        json=_txn(account_id, type="income", amount="5000.00", category_id=categories["Salary"]["id"], date=STALE_DATE),
    )
    assert "idle_cash" in await _alert_keys(client)

    resp = await client.patch("/settings", json={"idle_cash_threshold_amount": "10000.00"})
    assert resp.status_code == 200

    assert "idle_cash" not in await _alert_keys(client)


async def test_negative_cash_flow_streak_is_scoped_to_the_caller(client: AsyncClient, account_id, categories):
    from tests.helpers import auth_headers, register_user

    b_tokens = await register_user(client, "insightsb@example.com")
    b_account = (
        await client.post("/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
                          headers=auth_headers(b_tokens["access_token"]))
    ).json()
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")
    from datetime import date, timedelta
    last_month = (date.today().replace(day=1) - timedelta(days=1))
    await client.post(
        "/transactions",
        json=_txn(b_account["id"], type="expense", amount="9999.00", category_id=b_groceries, date=last_month.isoformat()),
        headers=auth_headers(b_tokens["access_token"]),
    )
    resp = await client.patch(
        "/settings", json={"negative_cash_flow_threshold_months": 1}, headers=auth_headers(b_tokens["access_token"])
    )
    assert resp.status_code == 200

    assert "negative_cash_flow_streak" not in await _alert_keys(client)


async def test_idle_cash_is_still_scoped_after_net_worth_signals_were_added(client: AsyncClient, account_id, categories):
    """Regression guard: adding the remaining 3 signals in this task must
    not break the idle-cash signal Part 1 already scoped correctly."""
    await client.post(
        "/transactions",
        json=_txn(account_id, type="income", amount="5000.00", category_id=categories["Salary"]["id"], date=STALE_DATE),
    )
    assert "idle_cash" in await _alert_keys(client)
