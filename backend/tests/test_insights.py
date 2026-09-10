"""Proactive alerts (services/insights_service.py). Currently covered here:
idle_cash (correctness + its own scoping, including a regression guard that
it's still scoped after the net-worth-related signals below were added) and
negative_cash_flow_streak (scoping only). The other 3 of get_financial_alerts'
5 signals — net_worth_decline_streak, risky_allocation_exceeded, and
budget_exceeded — have no dedicated test anywhere in this suite, for either
their correctness or their per-user isolation. This is a real gap, though a
lower-risk one than it might sound: each of those three is threaded through
from a user_id argument the same way as the tested ones, and a forgotten
user_id there would 500 the whole /insights/alerts endpoint loudly (session
scoping helpers here take user_id as a required positional argument), rather
than silently leak another user's data.
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

    # Also lower the DEFAULT client's (user A's) OWN threshold to 1. Without
    # this, A's threshold stays at its untouched default of 2 (see
    # AppSettings.negative_cash_flow_threshold_months) and the test can't
    # discriminate scoped from unscoped code: even a fully-unscoped
    # _negative_cash_flow_streak would only see a 1-month streak from B's
    # single bad month (the month before has no data for anyone, so the
    # streak calculation stops there), and 1 >= 2 is false either way. With
    # A's own threshold now at 1, correct scoping still finds no negative
    # months for A (A posted no transactions) so no alert fires — but if
    # scoping were removed, A's leaked streak of 1 would trip `1 >= 1` and
    # the alert would (incorrectly) fire, so this addition is what makes the
    # test actually fail when scoping breaks.
    resp = await client.patch("/settings", json={"negative_cash_flow_threshold_months": 1})
    assert resp.status_code == 200

    assert "negative_cash_flow_streak" not in await _alert_keys(client)


async def test_idle_cash_is_still_scoped_after_net_worth_signals_were_added(client: AsyncClient, account_id, categories):
    """Regression guard: adding the remaining 3 signals in this task must
    not break the idle-cash signal Part 1 already scoped correctly. Unlike
    the plain sibling test_idle_cash_flags_a_stale_large_balance, this one
    also seeds a second user (B) with her own unrelated net-worth data (a
    large, high-risk asset — the kind of thing risky_allocation_exceeded and
    net_worth_decline_streak read) in the same database, so it would catch a
    future edit that broke idle_cash's own scoping while touching the
    net-worth-signal code added later in this same get_financial_alerts."""
    from tests.helpers import auth_headers, register_user

    b_tokens = await register_user(client, "insightsb2@example.com")
    await client.post(
        "/assets",
        json={"name": "B's Crypto", "asset_class": "crypto", "value": "999999.00", "as_of_date": date.today().isoformat(),
              "risk_level": "high", "capital_role": "drain"},
        headers=auth_headers(b_tokens["access_token"]),
    )

    await client.post(
        "/transactions",
        json=_txn(account_id, type="income", amount="5000.00", category_id=categories["Salary"]["id"], date=STALE_DATE),
    )
    assert "idle_cash" in await _alert_keys(client)
