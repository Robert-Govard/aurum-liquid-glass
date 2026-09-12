"""Advice: curated, non-urgent financial notes — basic correctness (no
prior test file existed) plus per-user isolation."""
import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.models.user import User
from tests.helpers import auth_headers, register_user, txn_payload as _txn


@pytest.fixture(autouse=True)
async def _default_user_is_premium(request, client, test_sessionmaker):
    """This whole file exercises a Premium-gated router (see
    plan_service.py / deps.get_premium_user) — the client fixture's
    default user is Free by design (Task 2's limit tests need that), so
    promote it here for every test except the ones that specifically
    want the Free/402 case (marked @pytest.mark.free_tier below).

    Depends on `client` (even though it's unused directly) purely to force
    fixture ordering — autouse fixtures otherwise instantiate before the
    other fixtures a test requests, which here would run this UPDATE
    before `client` has even registered the "test@example.com" row it's
    meant to promote.
    """
    if "free_tier" in request.keywords:
        return
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "test@example.com").values(is_admin=True))
        await session.commit()


async def test_rising_category_advice_is_scoped_to_the_caller(client: AsyncClient, account_id, categories):
    """A category that's genuinely rising for user B must never surface as
    a `rising_category` advice item for user A.

    User A (the `client` fixture's default user) is given zero
    transactions anywhere in this test, so A's own current-month category
    totals are legitimately empty and no `rising_category` item can ever
    be computed for A honestly. User B, meanwhile, gets a real
    rising-category pattern: a steady modest spend in "Groceries" for
    each of the trailing 3 months, then a much larger spend this month —
    comfortably above RISING_CATEGORY_THRESHOLD_PERCENT. If
    `_category_expense_totals` ever lost its `scoped()` call, it would
    merge every user's category_id -> amount rows into one dict; called
    for user A, that unscoped dict would include B's Groceries entries,
    A's (empty) totals would suddenly look non-empty, and B's rising
    pattern would get reported as A's advice. Asserting A sees no
    `rising_category` item at all is what catches that."""
    b_tokens = await register_user(client, "adviceb@example.com")
    b_account = (
        await client.post("/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
                          headers=auth_headers(b_tokens["access_token"]))
    ).json()
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")

    from datetime import date

    def _previous_month(year: int, month: int) -> tuple[int, int]:
        # Mirrors advice_service.py's own `_previous_month` helper so the
        # trailing-month transactions below land in exactly the months
        # the service will query — including the January -> December
        # year rollover.
        return (year - 1, 12) if month == 1 else (year, month - 1)

    today = date.today()
    year, month = today.year, today.month
    for _ in range(3):
        year, month = _previous_month(year, month)
        await client.post(
            "/transactions",
            # Day 5 is valid in every month, so this never has to special-case
            # short months (e.g. February) while walking backwards.
            json=_txn(b_account["id"], amount="50.00", category_id=b_groceries, date=date(year, month, 5).isoformat()),
            headers=auth_headers(b_tokens["access_token"]),
        )
    # Trailing average is 150.00 / 3 = 50.00; 500.00 this month is an 900%
    # increase, far past the 25% threshold — a genuine rising category for B.
    await client.post(
        "/transactions",
        json=_txn(b_account["id"], amount="500.00", category_id=b_groceries, date=today.isoformat()),
        headers=auth_headers(b_tokens["access_token"]),
    )

    resp = await client.get("/advice")
    assert resp.status_code == 200
    assert all(item["key"] != "rising_category" for item in resp.json()["items"])


async def test_unbudgeted_top_category_advice_is_scoped_to_the_caller(client: AsyncClient, account_id, categories):
    b_tokens = await register_user(client, "adviceb2@example.com")
    b_account = (
        await client.post("/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
                          headers=auth_headers(b_tokens["access_token"]))
    ).json()
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")
    from datetime import date
    today = date.today()
    await client.post(
        "/transactions",
        json=_txn(b_account["id"], amount="500.00", category_id=b_groceries, date=today.isoformat()),
        headers=auth_headers(b_tokens["access_token"]),
    )

    resp = await client.get("/advice")
    assert resp.status_code == 200
    unbudgeted = [item for item in resp.json()["items"] if item["key"] == "unbudgeted_top_category"]
    assert all(item["params"]["category"] != "Groceries" for item in unbudgeted)


@pytest.mark.free_tier
async def test_free_user_cannot_access_advice(client):
    resp = await client.get("/advice")
    assert resp.status_code == 402


async def test_premium_user_can_access_advice(client):
    resp = await client.get("/advice")
    assert resp.status_code == 200
