# Multi-Tenant Data Isolation — Part 3A (Analytics: Dashboard, Cash Flow, Reports, Net Worth, Advice, Insights) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every read-only analytics view (Dashboard, Cash Flow, Reports, Net
Worth, Advice) and the proactive Insights alerts stop aggregating across
every user in the database and start reflecting only the calling user's own
accounts, transactions, and assets.

**Architecture:** No schema changes in this plan — every table these six
services read (`accounts`, `categories`, `transactions`,
`transaction_splits`, `budgets`, `assets`, `asset_valuations`) already has a
nullable `user_id` from the three already-merged isolation plans (Part 1,
Part 2A, Part 2B). This plan is pure service/route wiring: thread
`current_user: User = Depends(get_current_user)` through six route files,
thread `user_id: int` through the service functions underneath them, and
scope every raw `select()` those functions run via `app/services/scoped.py`'s
`scoped()` helper (or a plain `.where(Model.user_id == user_id)` where the
query already isn't a bare `select(Model)` `scoped()` can wrap cleanly —
noted per-task where that applies). `transaction_splits` has no `user_id`
column of its own (by design, from Part 2A — it's reached only through its
parent `Transaction`), so every split query is scoped by joining to
`Transaction` and filtering `Transaction.user_id == user_id` there instead.

`category_rollup.py`'s `rollup_spending_by_top_level_category` is shared by
both `dashboard_service.py` and `reports_service.py` — it gets its own task
first, since both callers need its new signature.

`insights_service.py`'s `get_financial_alerts` already threads `user_id`
into two of its five signals (from Part 1's Task 8 and Task 11) — its
remaining three unscoped internal calls (`_negative_cash_flow_streak`,
`get_net_worth_summary(session, "all")`, `_idle_cash_account_count`) only
become fixable once `dashboard_service.py` and `net_worth_service.py` gain
real `user_id` parameters, so this plan's final task finishes that
conversion, closing out a gap this series has carried since Part 1.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Docker
Compose — same stack as the rest of this series; no new dependencies, no
migration.

**Spec:** [docs/superpowers/specs/2026-09-08-multi-tenant-backend-design.md](../specs/2026-09-08-multi-tenant-backend-design.md)

## Global Constraints

- No migration in this plan — every column already exists and is already
  nullable from earlier plans.
- Every listing/aggregation query goes through `scoped()` from
  `app/services/scoped.py`, or an equivalent explicit
  `.where(Model.user_id == user_id)` when the query shape doesn't fit
  `scoped()`'s `Select` signature directly (e.g. a query already selecting
  specific columns rather than the whole model — `scoped()` still works
  there since it only adds a `.where()` clause, but call this out
  per-task so the implementer isn't guessing).
- `transaction_splits` has no `user_id` column — scope split queries via
  `.join(Transaction, ...).where(Transaction.user_id == user_id)`.
- A category, asset, or budget looked up by id that belongs to another
  user (or doesn't exist) returns 404 for the report-single-category
  endpoint (`reports_service.get_category_spending_report`) — every other
  endpoint in this plan is a pure aggregation with no single-object lookup
  by id, so 404-vs-403 doesn't apply to them.
- `backup_service.py`, the final `NOT NULL` migration pass, and retiring
  `AURUM_BASIC_AUTH_USER`/`PASSWORD` remain explicitly OUT of this plan's
  scope — a future "Part 3B" (or later) plan.
- Existing tests for `dashboard`, `cash_flow`, and `reports` (the three
  routers that already have test files) must keep passing UNCHANGED — they
  all run against the `client` fixture's single auto-authenticated user, so
  adding `user_id` scoping must not alter behavior for a single-user
  scenario. `net_worth` and `advice` currently have NO test files at all;
  this plan adds one for each, covering both basic correctness (nothing
  existed to verify before) and cross-user isolation.

---

## Task 1: Scope `category_rollup.py` (shared by dashboard + reports)

**Files:**
- Modify: `backend/app/services/category_rollup.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_raw_category_contributions(session, *, transaction_type, start_date, end_date, user_id)`,
  `rollup_spending_by_top_level_category(session, *, transaction_type, start_date=None, end_date=None, user_id)` —
  both gain a required keyword-only `user_id: int` parameter. Callers in
  Task 2 (dashboard) and Task 4 (reports) both pass it.

- [ ] **Step 1: Write the failing test**

There's no dedicated test file for this shared helper (it's tested
indirectly through `dashboard`/`reports`) — add the isolation check to
`backend/tests/test_dashboard.py` since `rollup_spending_by_top_level_category`
is exercised there on every existing test:

```python
async def test_rollup_excludes_another_users_categories_and_transactions(client: AsyncClient, account_id, categories):
    from tests.helpers import auth_headers, register_user

    b_tokens = await register_user(client, "dashb@example.com")
    b_account = (
        await client.post("/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
                          headers=auth_headers(b_tokens["access_token"]))
    ).json()
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")
    await client.post(
        "/transactions",
        json=_txn(b_account["id"], amount="500.00", category_id=b_groceries, date="2026-08-01"),
        headers=auth_headers(b_tokens["access_token"]),
    )

    await client.post(
        "/transactions", json=_txn(account_id, amount="75.00", category_id=categories["Groceries"]["id"], date="2026-08-01")
    )

    resp = await client.get("/dashboard/summary", params={"year": 2026, "month": 8})
    breakdown = {row["name"]: row for row in resp.json()["spending_by_category"]}
    assert money(breakdown["Groceries"]["amount"]) == Decimal("75.00")  # not 575.00
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_dashboard.py -v -k test_rollup_excludes`
Expected: FAIL — user B's 500.00 currently leaks into user A's Groceries total.

- [ ] **Step 3: Scope the helper**

Modify `backend/app/services/category_rollup.py`. Add to imports:

```python
from app.services.scoped import scoped
```

Replace `_raw_category_contributions`:

```python
async def _raw_category_contributions(
    session: AsyncSession,
    *,
    transaction_type: TransactionType,
    start_date: date_ | None,
    end_date: date_ | None,
    user_id: int,
) -> list[tuple[int, int, Decimal]]:
    """(transaction_id, category_id, amount) for every category a
    transaction of this type/date-range contributed to. A plain transaction
    contributes one row (its own category); a split one contributes one row
    per split line — never both for the same transaction, since a
    transaction is either plain (category_id set, no splits) or split
    (category_id NULL, 2+ splits), enforced at write time."""
    plain_stmt = scoped(
        select(Transaction.id, Transaction.category_id, Transaction.amount), Transaction, user_id
    ).where(Transaction.type == transaction_type, Transaction.category_id.is_not(None))
    split_stmt = (
        select(TransactionSplit.transaction_id, TransactionSplit.category_id, TransactionSplit.amount)
        .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
        .where(
            Transaction.type == transaction_type,
            Transaction.user_id == user_id,
            TransactionSplit.category_id.is_not(None),
        )
    )
    if start_date is not None:
        plain_stmt = plain_stmt.where(Transaction.date >= start_date)
        split_stmt = split_stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        plain_stmt = plain_stmt.where(Transaction.date <= end_date)
        split_stmt = split_stmt.where(Transaction.date <= end_date)

    plain_rows = (await session.execute(plain_stmt)).all()
    split_rows = (await session.execute(split_stmt)).all()
    return [(r[0], r[1], r[2]) for r in plain_rows] + [(r[0], r[1], r[2]) for r in split_rows]
```

Replace `rollup_spending_by_top_level_category`:

```python
async def rollup_spending_by_top_level_category(
    session: AsyncSession,
    *,
    transaction_type: TransactionType,
    user_id: int,
    start_date: date_ | None = None,
    end_date: date_ | None = None,
) -> list[CategoryRollupItem]:
    """Every top-level category's total for the period, sorted by amount
    desc (category sort_order as tiebreak — same order the SQL-only version
    used to produce)."""
    contributions = await _raw_category_contributions(
        session, transaction_type=transaction_type, start_date=start_date, end_date=end_date, user_id=user_id
    )
    if not contributions:
        return []

    categories_by_id = {
        c.id: c for c in (await session.execute(scoped(select(Category), Category, user_id))).scalars().all()
    }

    amount_by_effective: dict[int, Decimal] = defaultdict(Decimal)
    txn_ids_by_effective: dict[int, set[int]] = defaultdict(set)
    # effective (top-level) category id -> {actual leaf category_id: amount}
    # — the leaf is the same as the effective id when a contribution was
    # filed directly on the parent, and a genuine child id otherwise.
    amount_by_leaf: dict[int, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for transaction_id, category_id, amount in contributions:
        category = categories_by_id.get(category_id)
        effective_id = category.parent_id if category and category.parent_id is not None else category_id
        amount_by_effective[effective_id] += amount
        amount_by_leaf[effective_id][category_id] += amount
        txn_ids_by_effective[effective_id].add(transaction_id)

    items: list[CategoryRollupItem] = []
    for effective_id, amount in amount_by_effective.items():
        category = categories_by_id.get(effective_id)
        leaf_amounts = amount_by_leaf[effective_id]
        children: list[CategoryRollupChildItem] = []
        if len(leaf_amounts) > 1:
            for leaf_id, leaf_amount in sorted(leaf_amounts.items(), key=lambda pair: -pair[1]):
                leaf_category = categories_by_id.get(leaf_id)
                children.append(
                    CategoryRollupChildItem(
                        category_id=leaf_id,
                        name=leaf_category.name if leaf_category else "?",
                        color=leaf_category.color if leaf_category else "#898781",
                        icon=leaf_category.icon if leaf_category else None,
                        amount=leaf_amount,
                    )
                )
        items.append(
            CategoryRollupItem(
                category_id=effective_id,
                name=category.name if category else "?",
                color=category.color if category else "#898781",
                icon=category.icon if category else None,
                sort_order=category.sort_order if category else 0,
                amount=amount,
                transaction_count=len(txn_ids_by_effective[effective_id]),
                children=children,
            )
        )
    items.sort(key=lambda item: (-item.amount, item.sort_order))
    return items
```

Note: `amount_by_effective`'s keys can only ever be ids of categories
whose owning transaction/split was already confirmed to belong to
`user_id` (via the scoped `_raw_category_contributions` above) — a
category id from a *different* user could theoretically appear as a
dict key here only if `categories_by_id` (also scoped) failed to
resolve it, which just falls back to the already-existing `"?"` /
`#898781` placeholder path, not a cross-user leak of a real name/color.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest tests/test_dashboard.py -v -k test_rollup_excludes`
Expected: PASS. (This will still fail at this point in isolation, since
`dashboard_service.py` hasn't been updated to pass `user_id` yet — see
Task 2. It's fine for this one test to stay red until Task 2 lands; the
plan text says so explicitly rather than leaving the implementer to
guess. Confirm the failure mode is a `TypeError: missing 1 required
keyword-only argument: 'user_id'` from `rollup_spending_by_top_level_category`'s
caller, not something else, then move on to Task 2.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/category_rollup.py backend/tests/test_dashboard.py
git commit -m "Изолировать сводку по категориям (category_rollup) по пользователю"
```

---

## Task 2: Scope `dashboard_service.py`

**Files:**
- Modify: `backend/app/services/dashboard_service.py`
- Modify: `backend/app/api/routes/dashboard.py`

**Interfaces:**
- Consumes: `rollup_spending_by_top_level_category(session, *, transaction_type, user_id, start_date=None, end_date=None)` (Task 1).
- Produces: `get_dashboard_summary(session, year, month, user_id)` — gains a required `user_id: int` positional parameter after `month`. `advice_service.py` (Task 6) and `insights_service.py` (Task 7) both call this and are updated in their own tasks.

- [ ] **Step 1: Verify Task 1's rollup test now needs this task to pass**

No new failing-test step needed here beyond what Task 1 already wrote —
Task 1's `test_rollup_excludes_another_users_categories_and_transactions`
is the test this task turns green. Confirm it's still red before
starting: `docker compose exec backend pytest tests/test_dashboard.py -v -k test_rollup_excludes` → FAIL.

- [ ] **Step 2: Scope the service**

Modify `backend/app/services/dashboard_service.py`. Add to imports:

```python
from app.services.scoped import scoped
```

Replace `get_dashboard_summary`:

```python
async def get_dashboard_summary(session: AsyncSession, year: int, month: int, user_id: int) -> DashboardSummary:
    start, end = _month_bounds(year, month)

    totals_stmt = scoped(
        select(Transaction.type, func.coalesce(func.sum(Transaction.amount), 0)), Transaction, user_id
    ).where(Transaction.date >= start, Transaction.date <= end).group_by(Transaction.type)
    totals_result = await session.execute(totals_stmt)
    totals: dict[TransactionType, Decimal] = {row[0]: row[1] for row in totals_result.all()}

    real_income = totals.get(TransactionType.INCOME, Decimal("0"))
    spent = totals.get(TransactionType.EXPENSE, Decimal("0"))
    transferred_out = totals.get(TransactionType.TRANSFER, Decimal("0"))

    # A subcategory's spending rolls up into its parent's slice, and a split
    # transaction's category_id=NULL means its category lives on its split
    # lines instead — rollup_spending_by_top_level_category handles both
    # the same way a plain transaction's category already was.
    rows = await rollup_spending_by_top_level_category(
        session, transaction_type=TransactionType.EXPENSE, start_date=start, end_date=end, user_id=user_id
    )

    top_rows, rest_rows = rows[:MAX_CHART_SLICES], rows[MAX_CHART_SLICES:]

    def _percent(amount: Decimal) -> float:
        return float(amount / spent * 100) if spent else 0.0

    spending_by_category = [
        CategoryBreakdownItem(
            category_id=row.category_id, name=row.name, color=row.color, icon=row.icon,
            amount=row.amount, percent=_percent(row.amount),
            children=[
                CategoryBreakdownChildItem(
                    category_id=child.category_id, name=child.name, color=child.color, icon=child.icon,
                    amount=child.amount,
                )
                for child in row.children
            ],
        )
        for row in top_rows
    ]

    if rest_rows:
        other_amount = sum((row.amount for row in rest_rows), Decimal("0"))
        spending_by_category.append(
            CategoryBreakdownItem(
                category_id=None, name="Other", color=OTHER_SLICE_COLOR, icon="more-horizontal",
                amount=other_amount, percent=_percent(other_amount),
            )
        )

    return DashboardSummary(
        year=year,
        month=month,
        real_income=real_income,
        spent=spent,
        net=real_income - spent,
        transferred_out=transferred_out,
        spending_by_category=spending_by_category,
    )
```

- [ ] **Step 3: Wire the route**

Modify `backend/app/api/routes/dashboard.py` — replace the whole file:

```python
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def read_dashboard_summary(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DashboardSummary:
    return await get_dashboard_summary(session, year, month, current_user.id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_dashboard.py -v`
Expected: PASS — every test in the file, including Task 1's isolation test.

- [ ] **Step 5: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: `test_advice.py` (doesn't exist yet) is irrelevant; but any
existing caller of `get_dashboard_summary` with the OLD 3-arg signature
will now break loudly. Confirm the only such caller left is
`advice_service.py` (`_savings_rate_trend_advice`, two calls) — this is
expected and is Task 6's job to fix, not this task's. Confirm failures
are confined to whatever test exists for advice today (none — there's no
`test_advice.py` yet) and that nothing else outside `test_dashboard.py`
regresses. If `insights_service.py` also calls it — check: it does not
call `get_dashboard_summary` directly today (only
`_negative_cash_flow_streak` does, and that's a private helper inside
`insights_service.py` itself, fixed in Task 7) — confirm this via
`grep -rn "get_dashboard_summary" backend/app/` before concluding no
other caller breaks.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dashboard_service.py backend/app/api/routes/dashboard.py
git commit -m "Изолировать сводку дашборда по пользователю"
```

---

## Task 3: Scope `cash_flow_service.py`

**Files:**
- Modify: `backend/app/services/cash_flow_service.py`
- Modify: `backend/app/api/routes/cash_flow.py`
- Modify: `backend/tests/test_cash_flow.py`

**Interfaces:**
- Produces: `get_cash_flow(session, start_date, end_date, user_id)` — gains a required `user_id: int` parameter after `end_date`. No other task in this plan calls this function.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_cash_flow.py`:

```python
async def test_cash_flow_excludes_another_users_transactions(client: AsyncClient, account_id, categories):
    from tests.helpers import auth_headers, register_user

    b_tokens = await register_user(client, "cashflowb@example.com")
    b_account = (
        await client.post("/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
                          headers=auth_headers(b_tokens["access_token"]))
    ).json()
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_salary = next(c["id"] for c in b_categories if c["name"] == "Salary")
    await client.post(
        "/transactions",
        json=txn_payload(b_account["id"], amount="9999.00", type="income", category_id=b_salary, date="2026-08-01"),
        headers=auth_headers(b_tokens["access_token"]),
    )

    salary_id = categories["Salary"]["id"]
    await client.post(
        "/transactions", json=txn_payload(account_id, amount="1000.00", type="income", category_id=salary_id, date="2026-08-01")
    )

    resp = await client.get("/cash-flow", params={"start_date": "2026-08-01", "end_date": "2026-08-31"})
    body = resp.json()
    assert money(body["total_income"]) == Decimal("1000.00")  # not 10999.00
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_cash_flow.py -v -k test_cash_flow_excludes`
Expected: FAIL — user B's 9999.00 leaks in.

- [ ] **Step 3: Scope the service**

Modify `backend/app/services/cash_flow_service.py`. Add to imports:

```python
from app.services.scoped import scoped
```

Replace `get_cash_flow`:

```python
async def get_cash_flow(
    session: AsyncSession, start_date: date_ | None, end_date: date_ | None, user_id: int
) -> CashFlowResponse:
    bounds_stmt = scoped(
        select(func.min(Transaction.date), func.max(Transaction.date)), Transaction, user_id
    ).where(Transaction.type != TransactionType.TRANSFER)
    if start_date:
        bounds_stmt = bounds_stmt.where(Transaction.date >= start_date)
    if end_date:
        bounds_stmt = bounds_stmt.where(Transaction.date <= end_date)
    min_date, max_date = (await session.execute(bounds_stmt)).one()

    effective_start = start_date or min_date
    effective_end = end_date or max_date

    empty = CashFlowResponse(
        start_date=effective_start,
        end_date=effective_end,
        points=[],
        total_income=Decimal("0"),
        total_expense=Decimal("0"),
        total_net=Decimal("0"),
    )
    if effective_start is None or effective_end is None:
        return empty

    rows_stmt = scoped(
        select(
            extract("year", Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
            Transaction.type,
            func.sum(Transaction.amount).label("amount"),
        ),
        Transaction,
        user_id,
    ).where(
        Transaction.type != TransactionType.TRANSFER,
        Transaction.date >= effective_start,
        Transaction.date <= effective_end,
    ).group_by("year", "month", Transaction.type)
    rows = (await session.execute(rows_stmt)).all()

    by_month: dict[tuple[int, int], dict[TransactionType, Decimal]] = defaultdict(dict)
    for year, month, tx_type, amount in rows:
        by_month[(int(year), int(month))][tx_type] = amount

    points: list[CashFlowPoint] = []
    year, month = effective_start.year, effective_start.month
    while (year, month) <= (effective_end.year, effective_end.month):
        totals = by_month.get((year, month), {})
        income = totals.get(TransactionType.INCOME, Decimal("0"))
        expense = totals.get(TransactionType.EXPENSE, Decimal("0"))
        points.append(CashFlowPoint(year=year, month=month, income=income, expense=expense, net=income - expense))
        year, month = _next_month(year, month)

    total_income = sum((p.income for p in points), Decimal("0"))
    total_expense = sum((p.expense for p in points), Decimal("0"))

    return CashFlowResponse(
        start_date=effective_start,
        end_date=effective_end,
        points=points,
        total_income=total_income,
        total_expense=total_expense,
        total_net=total_income - total_expense,
    )
```

- [ ] **Step 4: Wire the route**

Modify `backend/app/api/routes/cash_flow.py` — replace the whole file:

```python
from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.cash_flow import CashFlowResponse
from app.services.cash_flow_service import get_cash_flow

router = APIRouter(prefix="/cash-flow", tags=["cash-flow"])


@router.get("", response_model=CashFlowResponse)
async def read_cash_flow(
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CashFlowResponse:
    return await get_cash_flow(session, start_date, end_date, current_user.id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_cash_flow.py -v`
Expected: PASS — every test in the file.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/cash_flow_service.py backend/app/api/routes/cash_flow.py backend/tests/test_cash_flow.py
git commit -m "Изолировать отчёт cash flow по пользователю"
```

---

## Task 4: Scope `reports_service.py`

**Files:**
- Modify: `backend/app/services/reports_service.py`
- Modify: `backend/app/api/routes/reports.py`
- Modify: `backend/tests/test_reports.py`

**Interfaces:**
- Consumes: `rollup_spending_by_top_level_category(session, *, transaction_type, user_id, start_date=None, end_date=None)` (Task 1).
- Produces: `get_category_spending_report(session, category_id, start_date, end_date, user_id)`,
  `get_category_ranking_report(session, kind, start_date, end_date, user_id)` — both gain a required `user_id: int` parameter.

- [ ] **Step 1: Write the failing tests**

Read `backend/tests/test_reports.py` first to match its exact existing
helper/fixture conventions (it already exists — do not guess its
imports). Append:

```python
async def test_category_spending_report_404s_for_another_users_category(client: AsyncClient, categories):
    from tests.helpers import auth_headers, register_user

    b_tokens = await register_user(client, "reportb@example.com")
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")

    resp = await client.get("/reports/category-spending", params={"category_id": b_groceries})
    assert resp.status_code == 404


async def test_category_ranking_report_excludes_another_users_transactions(client: AsyncClient, account_id, categories):
    from tests.helpers import auth_headers, register_user

    b_tokens = await register_user(client, "reportb2@example.com")
    b_account = (
        await client.post("/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
                          headers=auth_headers(b_tokens["access_token"]))
    ).json()
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")
    await client.post(
        "/transactions",
        json=_txn(b_account["id"], amount="9999.00", category_id=b_groceries, date="2026-08-01"),
        headers=auth_headers(b_tokens["access_token"]),
    )

    await client.post(
        "/transactions", json=_txn(account_id, amount="50.00", category_id=categories["Groceries"]["id"], date="2026-08-01")
    )

    resp = await client.get("/reports/category-ranking", params={"kind": "expense"})
    groceries_row = next(item for item in resp.json()["items"] if item["name"] == "Groceries")
    assert money(groceries_row["amount"]) == Decimal("50.00")  # not 10049.00
```

`test_reports.py` already imports `money` and `txn_payload as _txn` at
the top of the file (confirmed by reading it directly) — both tests
above use that existing `_txn` alias and `money`, no new imports needed
beyond `auth_headers`/`register_user`, which are imported inline per
test above (matching this series' established convention elsewhere).

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_reports.py -v -k "another_users"`
Expected: FAIL.

- [ ] **Step 3: Scope the service**

Modify `backend/app/services/reports_service.py`. Add to imports:

```python
from app.services.scoped import get_owned_or_404, scoped
```

Replace `get_category_spending_report`:

```python
async def get_category_spending_report(
    session: AsyncSession, category_id: int, start_date: date_ | None, end_date: date_ | None, user_id: int
) -> CategorySpendingReport:
    category = await get_owned_or_404(session, Category, category_id, user_id, detail="Category not found")

    # A top-level category's own report folds in its subcategories' spending
    # too (same rollup as the Dashboard breakdown); a subcategory picked
    # directly shows just its own transactions — there's nothing beneath it.
    category_ids: list[int] = [category_id]
    if category.parent_id is None:
        child_ids = (
            await session.execute(
                scoped(select(Category.id), Category, user_id).where(Category.parent_id == category_id)
            )
        ).scalars().all()
        category_ids.extend(child_ids)

    # Plain transactions filed directly under one of these categories, plus
    # split lines that assign part of a transaction to one of them — same
    # two sources category_rollup.py unions for the Dashboard/ranking report.
    # category_ids is already scoped to this user's own categories (via
    # get_owned_or_404 above and the scoped child-lookup above), so no
    # separate user_id filter is needed on Transaction.category_id.in_(...)
    # itself — but the split_stmt still joins Transaction to double-check
    # the parent transaction is this user's, since a split's own row has no
    # user_id column of its own (see Global Constraints).
    plain_stmt = scoped(
        select(Transaction.id, Transaction.date, Transaction.amount), Transaction, user_id
    ).where(Transaction.category_id.in_(category_ids))
    split_stmt = (
        select(TransactionSplit.transaction_id, Transaction.date, TransactionSplit.amount)
        .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
        .where(TransactionSplit.category_id.in_(category_ids), Transaction.user_id == user_id)
    )
    if start_date:
        plain_stmt = plain_stmt.where(Transaction.date >= start_date)
        split_stmt = split_stmt.where(Transaction.date >= start_date)
    if end_date:
        plain_stmt = plain_stmt.where(Transaction.date <= end_date)
        split_stmt = split_stmt.where(Transaction.date <= end_date)

    plain_rows = (await session.execute(plain_stmt)).all()
    split_rows = (await session.execute(split_stmt)).all()
    contributions = [(r[0], r[1], r[2]) for r in plain_rows] + [(r[0], r[1], r[2]) for r in split_rows]

    empty = CategorySpendingReport(
        category_id=category.id,
        category_name=category.name,
        category_color=category.color,
        category_icon=category.icon,
        start_date=start_date,
        end_date=end_date,
        total_amount=Decimal("0"),
        transaction_count=0,
        average_per_month=Decimal("0"),
        series=[],
    )
    if not contributions:
        return empty

    dates = [txn_date for _, txn_date, _ in contributions]
    effective_start = start_date or min(dates)
    effective_end = end_date or max(dates)

    by_month: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for _, txn_date, amount in contributions:
        by_month[(txn_date.year, txn_date.month)] += amount

    total_amount = sum((amount for _, _, amount in contributions), Decimal("0"))
    # Distinct transactions, not rows — a transaction split across two of
    # these categories (e.g. parent + one of its children) must count once,
    # the same as a plain transaction filed under just one of them.
    total_count = len({transaction_id for transaction_id, _, _ in contributions})

    series: list[CategorySpendingPoint] = []
    year, month = effective_start.year, effective_start.month
    while (year, month) <= (effective_end.year, effective_end.month):
        series.append(CategorySpendingPoint(year=year, month=month, amount=by_month.get((year, month), Decimal("0"))))
        year, month = _next_month(year, month)

    months_count = len(series)
    average_per_month = (total_amount / months_count).quantize(Decimal("0.01")) if months_count else Decimal("0")

    return CategorySpendingReport(
        category_id=category.id,
        category_name=category.name,
        category_color=category.color,
        category_icon=category.icon,
        start_date=effective_start,
        end_date=effective_end,
        total_amount=total_amount,
        transaction_count=total_count,
        average_per_month=average_per_month,
        series=series,
    )
```

Note: `get_category_spending_report` previously returned 404 via a plain
`HTTPException` when `session.get(Category, category_id)` came back
`None` — the `HTTPException` import stays needed for nothing else in
this file after this change (check with `grep -n HTTPException` after
editing; if `get_owned_or_404` is now the only source of the 404, the
`from fastapi import HTTPException` import line can be removed — but
only if nothing else in the file still raises `HTTPException` directly).

Replace `get_category_ranking_report`:

```python
async def get_category_ranking_report(
    session: AsyncSession, kind: CategoryKind, start_date: date_ | None, end_date: date_ | None, user_id: int
) -> CategoryRankingReport:
    """All categories of one kind, ranked by total spent/earned over an
    arbitrary period — "which category costs the most" across the whole
    range, unlike the month-scoped Dashboard breakdown or the
    single-category detail above."""
    # A transaction's type already restricts it to categories of the
    # matching kind (enforced at write time by _ensure_category_matches_type
    # in routes/transactions.py), so filtering by transaction_type below is
    # enough — no separate kind filter needed, and the shared rollup already
    # unions plain transactions with split lines the same way the Dashboard
    # breakdown does.
    rows = await rollup_spending_by_top_level_category(
        session, transaction_type=_KIND_TO_TRANSACTION_TYPE[kind], start_date=start_date, end_date=end_date, user_id=user_id
    )
    total_amount = sum((row.amount for row in rows), Decimal("0"))

    def _percent(amount: Decimal) -> float:
        return float(amount / total_amount * 100) if total_amount else 0.0

    items = [
        CategoryRankingItem(
            category_id=row.category_id,
            name=row.name,
            color=row.color,
            icon=row.icon,
            amount=row.amount,
            percent=_percent(row.amount),
            transaction_count=row.transaction_count,
            children=[
                CategoryRankingChildItem(
                    category_id=child.category_id, name=child.name, color=child.color, icon=child.icon,
                    amount=child.amount,
                )
                for child in row.children
            ],
        )
        for row in rows
    ]

    return CategoryRankingReport(start_date=start_date, end_date=end_date, total_amount=total_amount, items=items)
```

- [ ] **Step 4: Wire the routes**

Modify `backend/app/api/routes/reports.py` — replace the whole file:

```python
from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.enums import CategoryKind
from app.models.user import User
from app.schemas.reports import CategoryRankingReport, CategorySpendingReport
from app.services.reports_service import get_category_ranking_report, get_category_spending_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/category-spending", response_model=CategorySpendingReport)
async def read_category_spending_report(
    category_id: int,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CategorySpendingReport:
    return await get_category_spending_report(session, category_id, start_date, end_date, current_user.id)


@router.get("/category-ranking", response_model=CategoryRankingReport)
async def read_category_ranking_report(
    kind: CategoryKind = CategoryKind.EXPENSE,
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CategoryRankingReport:
    return await get_category_ranking_report(session, kind, start_date, end_date, current_user.id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_reports.py -v`
Expected: PASS — every test in the file.

- [ ] **Step 6: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS — `reports_service.py`'s only other caller of note is
none (`get_category_spending_report`/`get_category_ranking_report` are
leaf functions, not called by any other service in this codebase —
confirm via `grep -rn "get_category_spending_report\|get_category_ranking_report" backend/app/`
before concluding this).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/reports_service.py backend/app/api/routes/reports.py backend/tests/test_reports.py
git commit -m "Изолировать отчёты по категориям по пользователю"
```

---

## Task 5: Scope `net_worth_service.py`

**Files:**
- Modify: `backend/app/services/net_worth_service.py`
- Modify: `backend/app/api/routes/net_worth.py`
- Create: `backend/tests/test_net_worth.py`

**Interfaces:**
- Produces: `get_net_worth_summary(session, range_key, user_id)` — gains a
  required `user_id: int` parameter. Every private helper
  (`_cash_cumulative_events`, `_asset_events_and_class_totals`,
  `_capital_role_summary`, `_risk_level_summary`) also gains it.
  `insights_service.py` (Task 7) calls `get_net_worth_summary` and is
  updated in its own task.

- [ ] **Step 1: Write the failing tests**

No test file exists for this router yet. Create
`backend/tests/test_net_worth.py`:

```python
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

    high_risk = next(r for r in body["risk_levels"] if r["risk_level"] == "high")
    assert money(high_risk["total_value"]) == Decimal("0")  # B's asset must not count here
```

Adjust field names to whatever `app/schemas/net_worth.py` actually
defines if any of the above don't match exactly — read that file first
if unsure (`CapitalRoleSummary`/`RiskLevelSummary`'s exact field names
are used verbatim from `net_worth_service.py`'s own construction code,
already shown in this task's Step 3 below).

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_net_worth.py -v`
Expected: FAIL (no `user_id` scoping exists yet — every test currently
aggregates across all registered users).

- [ ] **Step 3: Scope the service**

Modify `backend/app/services/net_worth_service.py`. Add to imports:

```python
from app.services.scoped import scoped
```

Replace `_cash_cumulative_events`:

```python
async def _cash_cumulative_events(session: AsyncSession, user_id: int) -> list[tuple[date_, Decimal]]:
    accounts_result = await session.execute(scoped(select(Account.id, Account.type), Account, user_id))
    cash_account_ids = {acc_id for acc_id, acc_type in accounts_result.all() if acc_type in CASH_ACCOUNT_TYPES}

    txns_result = await session.execute(
        scoped(
            select(Transaction.date, Transaction.type, Transaction.amount, Transaction.account_id, Transaction.transfer_account_id),
            Transaction,
            user_id,
        )
    )

    delta_by_date: dict[date_, Decimal] = defaultdict(Decimal)
    for tx_date, tx_type, amount, account_id, transfer_account_id in txns_result.all():
        if tx_type == TransactionType.INCOME and account_id in cash_account_ids:
            delta_by_date[tx_date] += amount
        elif tx_type == TransactionType.EXPENSE and account_id in cash_account_ids:
            delta_by_date[tx_date] -= amount
        elif tx_type == TransactionType.TRANSFER:
            if account_id in cash_account_ids:
                delta_by_date[tx_date] -= amount
            if transfer_account_id in cash_account_ids:
                delta_by_date[tx_date] += amount

    events: list[tuple[date_, Decimal]] = []
    running = Decimal("0")
    for day in sorted(delta_by_date):
        running += delta_by_date[day]
        events.append((day, running))
    return events
```

Note: `transfer_account_id` is read from an already-`user_id`-scoped
`Transaction` row, and Part 2A's write-time enforcement (verified in
that plan's final review) guarantees `transfer_account_id` always
refers to one of THIS SAME user's own accounts — so checking
`transfer_account_id in cash_account_ids` (itself computed from a
scoped `Account` query) never needs its own extra filter, consistent
with this whole series' "globally unique id is safe to leave unfiltered
once the write path enforces ownership" reasoning.

Replace `_asset_events_and_class_totals`:

```python
async def _asset_events_and_class_totals(
    session: AsyncSession, user_id: int
) -> tuple[list[tuple[date_, Decimal]], dict[AssetClass, Decimal], dict[int, Decimal]]:
    asset_class_result = await session.execute(scoped(select(Asset.id, Asset.asset_class), Asset, user_id))
    asset_class_map = dict(asset_class_result.all())

    # asset_class_map's keys are already scoped to this user's own assets
    # (query above) — the valuations query below joins against those ids
    # rather than re-filtering AssetValuation directly, since a valuation
    # row's own ownership always matches its parent asset's (enforced at
    # write time, see routes/assets.py/crypto_service.py's Part 2B).
    valuations_result = await session.execute(
        select(AssetValuation.asset_id, AssetValuation.as_of_date, AssetValuation.value)
        .where(AssetValuation.asset_id.in_(asset_class_map.keys()))
        .order_by(AssetValuation.as_of_date)
    )
    rows = valuations_result.all()

    current_by_asset: dict[int, Decimal] = {}
    events: list[tuple[date_, Decimal]] = []
    for day, group in groupby(rows, key=lambda row: row[1]):
        for asset_id, _, value in group:
            current_by_asset[asset_id] = value
        events.append((day, sum(current_by_asset.values(), Decimal("0"))))

    class_totals: dict[AssetClass, Decimal] = defaultdict(Decimal)
    for asset_id, value in current_by_asset.items():
        asset_class = asset_class_map.get(asset_id)
        if asset_class is not None:
            class_totals[asset_class] += value

    return events, class_totals, current_by_asset
```

Important edge case: if `asset_class_map` is empty (user has zero
assets), `AssetValuation.asset_id.in_([])` is a valid, always-false SQL
condition (returns no rows) — this matches the function's pre-existing
behavior for a fresh database with zero assets, so no special-case
branch is needed.

Replace `_capital_role_summary`:

```python
async def _capital_role_summary(
    session: AsyncSession, current_by_asset: dict[int, Decimal], user_id: int
) -> list[CapitalRoleSummary]:
    """Cross-cuts the same assets by how the user tagged them (income /
    neutral / drain) instead of by asset class — always all three roles,
    even at zero, so the block reads as a fixed scale rather than a list
    that shuffles as assets are added."""
    roles_result = await session.execute(
        scoped(select(Asset.id, Asset.capital_role, Asset.monthly_cash_flow), Asset, user_id)
    )

    totals_value: dict[CapitalRole, Decimal] = defaultdict(Decimal)
    totals_flow: dict[CapitalRole, Decimal] = defaultdict(Decimal)
    counts: dict[CapitalRole, int] = defaultdict(int)
    for asset_id, role, cash_flow in roles_result.all():
        totals_value[role] += current_by_asset.get(asset_id, Decimal("0"))
        totals_flow[role] += cash_flow or Decimal("0")
        counts[role] += 1

    return [
        CapitalRoleSummary(
            role=role.value,
            label=_ROLE_META[role][0],
            color=_ROLE_META[role][1],
            total_value=totals_value.get(role, Decimal("0")),
            monthly_cash_flow=totals_flow.get(role, Decimal("0")),
            count=counts.get(role, 0),
        )
        for role in CapitalRole
    ]
```

Replace `_risk_level_summary`:

```python
async def _risk_level_summary(
    session: AsyncSession, current_by_asset: dict[int, Decimal], cash_today: Decimal, user_id: int
) -> list[RiskLevelSummary]:
    """Cross-cuts Cash + assets by user-tagged risk of loss — unlike
    capital_roles, Cash participates here: it's the zero-risk anchor an
    80/20-style allocation rule ("80% of capital at zero risk, at most 20%
    exposed") is measured against. Always all three tiers, even at zero,
    same reasoning as capital_roles. Each tier's item list *is* its
    diversification view — a tier that's one holding at 100% is
    concentrated, several even-sized holdings aren't, no separate index."""
    assets_result = await session.execute(scoped(select(Asset.id, Asset.name, Asset.risk_level), Asset, user_id))
    asset_rows = assets_result.all()

    totals: dict[RiskLevel, Decimal] = defaultdict(Decimal)
    items_by_level: dict[RiskLevel, list[tuple[str, str, Decimal]]] = defaultdict(list)

    if cash_today:
        totals[RiskLevel.LOW] += cash_today
        items_by_level[RiskLevel.LOW].append(("cash", _CLASS_META["cash"][0], cash_today))

    for asset_id, name, risk_level in asset_rows:
        value = current_by_asset.get(asset_id, Decimal("0"))
        if value == 0:
            continue
        totals[risk_level] += value
        items_by_level[risk_level].append((f"asset:{asset_id}", name, value))

    grand_total = sum(totals.values(), Decimal("0"))

    def _share(amount: Decimal, denominator: Decimal) -> float:
        return float(amount / denominator * 100) if denominator else 0.0

    summaries = []
    for level in RiskLevel:
        tier_total = totals.get(level, Decimal("0"))
        items = [
            RiskLevelItem(key=key, name=name, amount=amount, percent=_share(amount, tier_total))
            for key, name, amount in sorted(items_by_level.get(level, []), key=lambda item: item[2], reverse=True)
        ]
        summaries.append(
            RiskLevelSummary(
                risk_level=level.value,
                label=_RISK_META[level][0],
                color=_RISK_META[level][1],
                total_value=tier_total,
                percent=_share(tier_total, grand_total),
                items=items,
            )
        )
    return summaries
```

Replace `get_net_worth_summary`:

```python
async def get_net_worth_summary(session: AsyncSession, range_key: str, user_id: int) -> NetWorthSummary:
    today = date_.today()
    cash_events = await _cash_cumulative_events(session, user_id)
    asset_events, class_totals, current_by_asset = await _asset_events_and_class_totals(session, user_id)
    capital_roles = await _capital_role_summary(session, current_by_asset, user_id)

    start = _resolve_start_date(range_key, cash_events, asset_events, today)

    cash_series = _daily_series(cash_events, start, today)
    asset_series = _daily_series(asset_events, start, today)
    series = [
        NetWorthPoint(date=c.date, value=c.value + a.value) for c, a in zip(cash_series, asset_series, strict=True)
    ]

    current = series[-1].value if series else Decimal("0")
    start_value = series[0].value if series else Decimal("0")
    change_amount = current - start_value
    change_percent = float(change_amount / start_value * 100) if start_value else None

    # cash_events entries are already cumulative — the last one *is* today's total.
    cash_today = cash_events[-1][1] if cash_events else Decimal("0")
    risk_levels = await _risk_level_summary(session, current_by_asset, cash_today, user_id)

    total = cash_today + sum(class_totals.values(), Decimal("0"))

    def _percent(amount: Decimal) -> float:
        return float(amount / total * 100) if total else 0.0

    breakdown = []
    name, color, icon = _CLASS_META["cash"]
    breakdown.append(NetWorthBreakdownItem(key="cash", name=name, color=color, icon=icon, amount=cash_today, percent=_percent(cash_today)))
    for asset_class in AssetClass:
        name, color, icon = _CLASS_META[asset_class.value]
        amount = class_totals.get(asset_class, Decimal("0"))
        breakdown.append(
            NetWorthBreakdownItem(key=asset_class.value, name=name, color=color, icon=icon, amount=amount, percent=_percent(amount))
        )

    return NetWorthSummary(
        range=range_key,
        current=current,
        change_amount=change_amount,
        change_percent=change_percent,
        series=series,
        breakdown=breakdown,
        capital_roles=capital_roles,
        risk_levels=risk_levels,
    )
```

- [ ] **Step 4: Wire the route**

Modify `backend/app/api/routes/net_worth.py` — replace the whole file:

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.net_worth import NetWorthSummary
from app.services.net_worth_service import RANGE_DAYS, get_net_worth_summary

router = APIRouter(prefix="/net-worth", tags=["net-worth"])

_VALID_RANGES = sorted(set(RANGE_DAYS) | {"all"})
_RANGE_PATTERN = f"^({'|'.join(_VALID_RANGES)})$"


@router.get("/summary", response_model=NetWorthSummary)
async def read_net_worth_summary(
    range: str = Query(default="30d", pattern=_RANGE_PATTERN),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> NetWorthSummary:
    return await get_net_worth_summary(session, range, current_user.id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_net_worth.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: `insights_service.py`'s `get_net_worth_summary(session, "all")`
call (2-arg, positional) will now break loudly (`TypeError`) — this is
expected, Task 7's job to fix. Confirm via
`grep -rn "get_net_worth_summary" backend/app/` that `insights_service.py`
is the ONLY other caller, and that the only test failures are in
`test_insights.py` (the 3 tests already unrelated to the idle-cash signal
per that file's own docstring may or may not fail depending on whether
they trigger the net-worth-decline code path — check the actual failure
list and confirm it's exactly this `TypeError`, not something else).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/net_worth_service.py backend/app/api/routes/net_worth.py backend/tests/test_net_worth.py
git commit -m "Изолировать сводку по капиталу (net worth) по пользователю"
```

---

## Task 6: Scope `advice_service.py`

**Files:**
- Modify: `backend/app/services/advice_service.py`
- Modify: `backend/app/api/routes/advice.py`
- Create: `backend/tests/test_advice.py`

**Interfaces:**
- Consumes: `get_dashboard_summary(session, year, month, user_id)` (Task 2).
- Produces: `get_advice(session, user_id)` — gains a required `user_id: int` parameter. `_category_expense_totals`, `_rising_category_advice`, `_unbudgeted_top_category_advice`, `_savings_rate_trend_advice` all gain it too.

- [ ] **Step 1: Write the failing tests**

No test file exists for this router yet. Create `backend/tests/test_advice.py`:

```python
"""Advice: curated, non-urgent financial notes — basic correctness (no
prior test file existed) plus per-user isolation."""
from httpx import AsyncClient

from tests.helpers import auth_headers, register_user, txn_payload as _txn


async def test_rising_category_advice_is_scoped_to_the_caller(client: AsyncClient, account_id, categories):
    """A category that's risen sharply for user B must never appear in
    user A's advice feed."""
    b_tokens = await register_user(client, "adviceb@example.com")
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
        json=_txn(b_account["id"], amount="1000.00", category_id=b_groceries, date=today.isoformat()),
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_advice.py -v`
Expected: FAIL, and also confirm `GET /advice` currently 500s (before
this task, `get_advice` still has the pre-Task-2 3-arg call broken by
Task 2's earlier change) — i.e. these tests are currently red for
"broken by an earlier task", not just "not yet isolated"; this task
fixes both at once.

- [ ] **Step 3: Scope the service**

Modify `backend/app/services/advice_service.py`. Add to imports:

```python
from app.services.scoped import scoped
```

Replace `_category_expense_totals`:

```python
async def _category_expense_totals(session: AsyncSession, year: int, month: int, user_id: int) -> dict[int, Decimal]:
    start, end = _month_bounds(year, month)
    stmt = scoped(
        select(Transaction.category_id, func.sum(Transaction.amount)), Transaction, user_id
    ).where(
        Transaction.type == TransactionType.EXPENSE,
        Transaction.category_id.is_not(None),
        Transaction.date >= start,
        Transaction.date <= end,
    ).group_by(Transaction.category_id)
    return {row[0]: row[1] for row in (await session.execute(stmt)).all()}
```

Replace `_rising_category_advice`:

```python
async def _rising_category_advice(session: AsyncSession, year: int, month: int, user_id: int) -> AdviceItem | None:
    """The expense category furthest above its own trailing-3-month average,
    if that's at least RISING_CATEGORY_THRESHOLD_PERCENT higher."""
    current_totals = await _category_expense_totals(session, year, month, user_id)
    if not current_totals:
        return None

    trailing_totals: dict[int, Decimal] = defaultdict(Decimal)
    y, m = year, month
    for _ in range(TRAILING_MONTHS):
        y, m = _previous_month(y, m)
        for cat_id, amount in (await _category_expense_totals(session, y, m, user_id)).items():
            trailing_totals[cat_id] += amount

    best: tuple[float, int, Decimal, Decimal] | None = None
    for cat_id, current in current_totals.items():
        average = trailing_totals.get(cat_id, Decimal("0")) / TRAILING_MONTHS
        if average <= 0:
            continue
        increase_percent = float((current - average) / average * 100)
        if increase_percent >= RISING_CATEGORY_THRESHOLD_PERCENT and (best is None or increase_percent > best[0]):
            best = (increase_percent, cat_id, current, average)

    if best is None:
        return None

    increase_percent, cat_id, current, average = best
    # cat_id came from current_totals, itself already scoped to this
    # user's own transactions above — a plain session.get is safe here,
    # it can only ever resolve to a category this same user owns (or, if
    # the category was somehow deleted mid-request, None, handled below).
    category = await session.get(Category, cat_id)
    if category is None:
        return None

    return AdviceItem(
        key="rising_category",
        tone="warning",
        params={
            "category": category.name,
            "percent": round(increase_percent),
            "current": float(current),
            "average": float(average),
        },
    )
```

Replace `_unbudgeted_top_category_advice`:

```python
async def _unbudgeted_top_category_advice(session: AsyncSession, year: int, month: int, user_id: int) -> AdviceItem | None:
    """This month's highest-spending expense category that has no budget."""
    current_totals = await _category_expense_totals(session, year, month, user_id)
    if not current_totals:
        return None

    budgeted_ids = {
        row[0] for row in (await session.execute(scoped(select(Budget.category_id), Budget, user_id))).all()
    }

    for cat_id, amount in sorted(current_totals.items(), key=lambda item: item[1], reverse=True):
        if cat_id in budgeted_ids:
            continue
        category = await session.get(Category, cat_id)  # safe: cat_id is from this user's own scoped totals
        if category is None:
            continue
        return AdviceItem(
            key="unbudgeted_top_category",
            tone="neutral",
            params={"category": category.name, "amount": float(amount)},
        )

    return None
```

Replace `_savings_rate_trend_advice`:

```python
async def _savings_rate_trend_advice(session: AsyncSession, year: int, month: int, user_id: int) -> AdviceItem | None:
    """This month's savings rate (net / real_income) vs. last month's, when
    the swing is large enough to be worth mentioning."""
    current = await get_dashboard_summary(session, year, month, user_id)
    prev_year, prev_month = _previous_month(year, month)
    previous = await get_dashboard_summary(session, prev_year, prev_month, user_id)

    if current.real_income <= 0 or previous.real_income <= 0:
        return None

    current_rate = float(current.net / current.real_income * 100)
    previous_rate = float(previous.net / previous.real_income * 100)
    diff = current_rate - previous_rate

    if abs(diff) < SAVINGS_RATE_TREND_THRESHOLD_POINTS:
        return None

    return AdviceItem(
        key="savings_rate_trend",
        tone="positive" if diff > 0 else "warning",
        params={"rate": round(current_rate), "diff": round(diff)},
    )
```

Replace `get_advice`:

```python
async def get_advice(session: AsyncSession, user_id: int) -> AdviceResponse:
    today = date.today()
    generators = (_rising_category_advice, _unbudgeted_top_category_advice, _savings_rate_trend_advice)

    items: list[AdviceItem] = []
    for generate in generators:
        item = await generate(session, today.year, today.month, user_id)
        if item is not None:
            items.append(item)

    return AdviceResponse(items=items)
```

- [ ] **Step 4: Wire the route**

Modify `backend/app/api/routes/advice.py` — replace the whole file:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.advice import AdviceResponse
from app.services.advice_service import get_advice

router = APIRouter(prefix="/advice", tags=["advice"])


@router.get("", response_model=AdviceResponse)
async def read_advice(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> AdviceResponse:
    return await get_advice(session, current_user.id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_advice.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS — `advice_service.py` has no other callers
(`grep -rn "get_advice" backend/app/` to confirm).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/advice_service.py backend/app/api/routes/advice.py backend/tests/test_advice.py
git commit -m "Изолировать советы (advice) по пользователю"
```

---

## Task 7: Finish scoping `insights_service.py`'s remaining signals

**Files:**
- Modify: `backend/app/services/insights_service.py`
- Modify: `backend/tests/test_insights.py`

**Interfaces:**
- Consumes: `get_dashboard_summary(session, year, month, user_id)` (Task 2),
  `get_net_worth_summary(session, range_key, user_id)` (Task 5).
- Produces: no new public interface — `get_financial_alerts(session, user_id)`'s
  own signature is unchanged (it already took `user_id`); this task only
  finishes threading it into the function's own internals.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_insights.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_insights.py -v`
Expected: `test_negative_cash_flow_streak_is_scoped_to_the_caller` FAILs
(user B's expense currently leaks into the calling user's streak count);
the regression-guard test should already PASS (it's testing existing,
correct behavior) — if it doesn't, investigate before proceeding, since
that would mean something is already broken independent of this task.

- [ ] **Step 3: Scope the remaining signals**

Modify `backend/app/services/insights_service.py`. Add to imports:

```python
from app.services.scoped import scoped
```

Replace `_negative_cash_flow_streak`:

```python
async def _negative_cash_flow_streak(session: AsyncSession, user_id: int) -> int:
    today = date.today()
    year, month = _previous_month(today.year, today.month)

    streak = 0
    for _ in range(MAX_LOOKBACK_MONTHS):
        summary = await get_dashboard_summary(session, year, month, user_id)
        if summary.net >= 0:
            break
        streak += 1
        year, month = _previous_month(year, month)
    return streak
```

Replace `_idle_cash_account_count`:

```python
async def _idle_cash_account_count(
    session: AsyncSession, threshold_amount: Decimal, threshold_days: int, user_id: int
) -> int:
    eligible_ids = set(
        (
            await session.execute(
                scoped(select(Account.id), Account, user_id).where(
                    Account.is_archived.is_(False), Account.type.in_(_IDLE_CASH_ACCOUNT_TYPES)
                )
            )
        )
        .scalars()
        .all()
    )
    if not eligible_ids:
        return 0

    # Same derivation account_service._account_balances uses — balance is
    # never stored, only ever summed from the full transaction history — plus
    # tracking the most recent date that touched each account along the way.
    rows = await session.execute(
        scoped(
            select(Transaction.type, Transaction.amount, Transaction.account_id, Transaction.transfer_account_id, Transaction.date),
            Transaction,
            user_id,
        )
    )
    balances: dict[int, Decimal] = defaultdict(Decimal)
    last_activity: dict[int, date] = {}

    def touch(account_id: int | None, tx_date: date) -> None:
        if account_id in eligible_ids and (account_id not in last_activity or tx_date > last_activity[account_id]):
            last_activity[account_id] = tx_date

    for tx_type, amount, account_id, transfer_account_id, tx_date in rows.all():
        if tx_type == TransactionType.INCOME:
            balances[account_id] += amount
        elif tx_type == TransactionType.EXPENSE:
            balances[account_id] -= amount
        elif tx_type == TransactionType.TRANSFER:
            balances[account_id] -= amount
            if transfer_account_id is not None:
                balances[transfer_account_id] += amount
        touch(account_id, tx_date)
        touch(transfer_account_id, tx_date)

    cutoff = date.today() - timedelta(days=threshold_days)
    return sum(
        1
        for account_id in eligible_ids
        if balances.get(account_id, Decimal("0")) >= threshold_amount
        and last_activity.get(account_id, cutoff) <= cutoff
    )
```

Replace `get_financial_alerts` — same body, but every remaining unscoped
call gains `user_id` and the stale comment block is replaced with an
accurate one:

```python
async def get_financial_alerts(session: AsyncSession, user_id: int) -> AlertsResponse:
    settings = await get_or_create_app_settings(session, user_id)
    alerts: list[FinancialAlert] = []

    cash_flow_streak = await _negative_cash_flow_streak(session, user_id)
    if cash_flow_streak >= settings.negative_cash_flow_threshold_months:
        alerts.append(
            FinancialAlert(
                key="negative_cash_flow_streak",
                severity="warning",
                params={"months": cash_flow_streak},
            )
        )

    net_worth_summary = await get_net_worth_summary(session, "all", user_id)

    net_worth_streak = _net_worth_decline_streak(net_worth_summary)
    if net_worth_streak >= settings.net_worth_decline_threshold_months:
        alerts.append(
            FinancialAlert(
                key="net_worth_decline_streak",
                severity="warning",
                params={"months": net_worth_streak},
            )
        )

    risky_percent = sum(tier.percent for tier in net_worth_summary.risk_levels if tier.risk_level != "low")
    if risky_percent > settings.risky_allocation_threshold_percent:
        alerts.append(
            FinancialAlert(
                key="risky_allocation_exceeded",
                severity="warning",
                params={"percent": round(risky_percent), "threshold": settings.risky_allocation_threshold_percent},
            )
        )

    today = date.today()
    # Every signal in this function is now scoped to the calling user:
    # settings/thresholds (get_or_create_app_settings, Part 1), budget
    # status (get_budget_status, Part 1), cash-flow streak and net-worth
    # decline/risky-allocation (get_dashboard_summary/get_net_worth_summary,
    # this plan's Task 2/Task 5), and idle cash (below, this same task).
    budget_status = await get_budget_status(session, today.year, today.month, user_id)
    over_budget_count = sum(1 for item in budget_status.items if item.is_over_budget)
    if over_budget_count > 0:
        alerts.append(
            FinancialAlert(
                key="budget_exceeded",
                severity="warning",
                params={"count": over_budget_count},
            )
        )

    idle_cash_count = await _idle_cash_account_count(
        session, settings.idle_cash_threshold_amount, settings.idle_cash_threshold_days, user_id
    )
    if idle_cash_count > 0:
        alerts.append(
            FinancialAlert(
                key="idle_cash",
                severity="warning",
                params={"count": idle_cash_count, "days": settings.idle_cash_threshold_days},
            )
        )

    return AlertsResponse(alerts=alerts)
```

Also update this file's module-level docstring if it references the
now-outdated "these signals are instance-wide" framing — read the
current docstring first; if it doesn't mention scoping status at all
(the version shown in this plan's research doesn't), no docstring edit
is required beyond the inline comment already replaced above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_insights.py -v`
Expected: PASS — every test in the file, old and new.

- [ ] **Step 5: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS, plus the 5 known `xfail`s (unchanged from Part 2B's
final state) — this is the last task in this plan, so this run should
show the whole suite green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/insights_service.py backend/tests/test_insights.py
git commit -m "Завершить изоляцию сигналов финансовых уведомлений (insights) по пользователю"
```

---

## Plan Self-Review Notes

- **Spec coverage:** Implements the "Authorization / data isolation"
  approach for the last five read-only analytics routers plus
  `insights_service.py`'s remaining three unscoped signals — the exact
  gap named in Part 2B's own "Next Plan" section as this series' Part 3
  starting point (dashboard/net_worth/cash_flow/reports/advice, plus
  finishing insights).
- **Type/interface consistency:** every service function's new `user_id:
  int` parameter position matches between where it's defined and where
  it's called across tasks (`get_dashboard_summary`'s `user_id` as the
  4th positional arg is used identically in Task 2's route, Task 6's
  `_savings_rate_trend_advice`, and Task 7's `_negative_cash_flow_streak`;
  `get_net_worth_summary`'s 3rd positional arg matches between Task 5's
  route and Task 7's `get_financial_alerts`;
  `rollup_spending_by_top_level_category`'s keyword-only `user_id` is
  passed as a keyword at both call sites, Task 2 and Task 4).
- **No placeholders:** every step contains complete, real code, verified
  against the actual current file contents read directly from the
  repository before this plan was written (not reconstructed from
  memory).

---

## Next Plan

**Part 3B (backup rework + cutover):** a full per-user rework of
`backup_service.py`/`routes/backup.py` (closing the 5 `xfail`-marked
restore-loses-`user_id` gaps this series has accumulated across Part 1,
Part 2A, and Part 2B); the final migration flipping every `user_id`
column added across Parts 1, 2A, 2B, and this plan to `NOT NULL`;
retiring `AURUM_BASIC_AUTH_USER`/`PASSWORD` and nginx's `auth_basic` (see
`docker-compose.yml`, `frontend/nginx.conf`,
`frontend/docker-entrypoint.d/20-basic-auth.sh`,
`frontend/src/components/auth/LoginGate.tsx`, `frontend/src/lib/auth.ts`) —
now safely supersedable since every backend route enforces real per-user
JWT auth. After that, frontend login/registration screens and the
originally-requested Android (Capacitor) app become unblocked.
