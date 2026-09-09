# Multi-Tenant Data Isolation — Part 2A (Transactions) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every user's transactions — the largest, most central domain
in the app, with splits, tags, and transfers — fully private to them,
including closing the specific cross-reference gaps (an unchecked
`account_id`/`category_id`/`tag_ids` letting one user attach a transaction
to another user's data) that the Part 1 plan's final review flagged as
live today.

**Architecture:** A nullable `user_id` column on `transactions` (no
column needed on `transaction_splits` or the `transaction_tags` join
table — both are only ever reached through a `Transaction` row, never
queried standalone, so scoping the parent is sufficient, same reasoning
already applied throughout Part 1). `routes/transactions.py` (which has
no separate service file — logic lives directly in the route, matching
the existing pattern for `categories`/`tags`) gets `current_user:
User = Depends(get_current_user)` threaded through every endpoint, uses
`scoped()`/`get_owned_or_404()` for the `Transaction` row itself, and —
this is the part Part 1 left as a known gap — every cross-reference
(`account_id`, `transfer_account_id`, `category_id`, each id in
`tag_ids`, and each split's `category_id`) is verified to belong to the
calling user before being attached to a transaction.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2 —
same stack as Part 1; no new dependencies.

**Spec:** [docs/superpowers/specs/2026-09-08-multi-tenant-backend-design.md](../specs/2026-09-08-multi-tenant-backend-design.md)

## Global Constraints

- `user_id` is added **nullable** on `transactions`, matching Part 1's
  precedent (a final NOT NULL pass happens once every remaining table is
  converted, in a later "Part 3" plan).
- Every listing/lookup query against `Transaction` goes through
  `scoped()`/`get_owned_or_404()` (already built in Part 1,
  `app/services/scoped.py`) — no hand-written `.where(user_id == ...)`.
- A `Transaction` row that exists but belongs to another user returns
  404, not 403.
- **Every cross-reference on write must be ownership-checked, not just
  existence-checked**: `account_id`, `transfer_account_id`, `category_id`
  (on the transaction itself and on every split), and every id in
  `tag_ids`. A reference to an id that exists but belongs to someone else
  is rejected the same way a reference to a nonexistent id is (400 for
  category/tag — matching this file's existing error shape for bad
  references — 404 for account/transfer-account, matching the
  `get_owned_or_404` convention used for the primary resource elsewhere
  in this plan and Part 1). This closes the exact gap Part 1's final
  review identified: today, `routes/transactions.py` has no auth
  dependency at all, so any cross-reference works; once auth is added
  without ownership checks, an authenticated user could still attach
  their transaction to someone else's account/category/tags. This plan
  closes both at once — there is no intermediate "authenticated but still
  cross-referenceable" state to ship.
- `budget_service.get_budget_status`'s `Transaction`/`TransactionSplit`
  joins (added in Part 1's Task 8) stay unfiltered by `user_id` — this
  remains safe under the ownership-checked-cross-reference rule above:
  since every transaction's `category_id` is now guaranteed to belong to
  the same user who created the transaction, filtering by "categories
  this user owns" (already how `get_budget_status` works) transitively
  can never pull in another user's transactions.
- Known, accepted, unrelated: `tests/test_backup.py`'s one pre-existing
  failure (categories losing `user_id` on restore, deferred to Part 3) is
  not this plan's concern — it will remain red throughout this plan's
  execution, exactly as it was throughout Part 1's.

---

## Task 1: Migration — `user_id` on `transactions`

**Files:**
- Create: `backend/alembic/versions/e7c4a9f1b620_add_user_id_to_transactions.py`
- Modify: `backend/app/models/transaction.py`

**Interfaces:**
- Produces: `Transaction.user_id: Mapped[int | None]` (FK → `users.id`,
  `ondelete="CASCADE"`, nullable, indexed).

- [ ] **Step 1: Add `user_id` to the model**

Modify `backend/app/models/transaction.py` — add `ForeignKey` to the
existing `from sqlalchemy import Date, Enum, ForeignKey, Numeric, String,
Text` import line (already there), and add after `date`:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

- [ ] **Step 2: Write the migration**

The current head is `a3f7c2e9b148` (Part 1's `add_user_id_to_core_tables`).
Create `backend/alembic/versions/e7c4a9f1b620_add_user_id_to_transactions.py`:

```python
"""add user_id to transactions

Revision ID: e7c4a9f1b620
Revises: a3f7c2e9b148
Create Date: 2026-09-09 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c4a9f1b620'
down_revision: Union[str, None] = 'a3f7c2e9b148'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_transactions_user_id', 'transactions', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_transactions_user_id', 'transactions', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_transactions_user_id', table_name='transactions')
    op.drop_constraint('fk_transactions_user_id', 'transactions', type_='foreignkey')
    op.drop_column('transactions', 'user_id')
```

- [ ] **Step 3: Verify the migration runs both ways**

Run: `docker compose exec backend alembic upgrade head`, then `docker compose exec backend alembic downgrade -1`, then `docker compose exec backend alembic upgrade head` again.
Expected: all three succeed, ending at `head`.

- [ ] **Step 4: Run the full test suite**

Run: `docker compose exec backend pytest -v`
Expected: 182 passed, 1 failed — the same known, already-ledgered
`test_backup.py` failure from Part 1, unchanged. Nothing in application
code reads the new column yet.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/e7c4a9f1b620_add_user_id_to_transactions.py backend/app/models/transaction.py
git commit -m "Добавить nullable user_id в transactions"
```

---

## Task 2: Wire `transactions` — scoping and cross-reference ownership

**Files:**
- Modify: `backend/app/api/routes/transactions.py`
- Modify: `backend/tests/test_transactions.py`

**Interfaces:**
- Consumes: `get_current_user` (`app/api/deps.py`), `scoped`,
  `get_owned_or_404` (`app/services/scoped.py`).
- Produces: every route in this file requires
  `current_user: User = Depends(get_current_user)`. No new functions are
  exported for other files to import — this router already has no
  service layer, and nothing else in the codebase imports from it.

- [ ] **Step 1: Write the failing isolation tests**

Append to `backend/tests/test_transactions.py`:

```python
from tests.helpers import auth_headers, register_user


async def test_user_a_cannot_see_user_bs_transaction(client, account_id):
    a_txn = (await client.post("/transactions", json=_txn(account_id))).json()

    b_tokens = await register_user(client, "txnb@example.com")
    b_account = (
        await client.post(
            "/accounts",
            json={"name": "B's", "type": "checking", "currency": "USD"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()
    b_txn = (
        await client.post(
            "/transactions", json=_txn(b_account["id"]), headers=auth_headers(b_tokens["access_token"])
        )
    ).json()

    a_list = (await client.get("/transactions")).json()["items"]
    assert [t["id"] for t in a_list] == [a_txn["id"]]

    b_list = (await client.get("/transactions", headers=auth_headers(b_tokens["access_token"]))).json()["items"]
    assert [t["id"] for t in b_list] == [b_txn["id"]]


async def test_user_a_cannot_update_or_delete_user_bs_transaction(client):
    b_tokens = await register_user(client, "txnb2@example.com")
    b_account = (
        await client.post(
            "/accounts",
            json={"name": "B's", "type": "checking", "currency": "USD"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()
    b_txn = (
        await client.post(
            "/transactions", json=_txn(b_account["id"]), headers=auth_headers(b_tokens["access_token"])
        )
    ).json()

    assert (await client.patch(f"/transactions/{b_txn['id']}", json={"amount": "1.00"})).status_code == 404
    assert (await client.delete(f"/transactions/{b_txn['id']}")).status_code == 404


async def test_cannot_create_a_transaction_against_another_users_account(client):
    b_tokens = await register_user(client, "txnb3@example.com")
    b_account = (
        await client.post(
            "/accounts",
            json={"name": "B's", "type": "checking", "currency": "USD"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    resp = await client.post("/transactions", json=_txn(b_account["id"]))
    assert resp.status_code == 404


async def test_cannot_create_a_transfer_to_another_users_account(client, account_id):
    b_tokens = await register_user(client, "txnb4@example.com")
    b_account = (
        await client.post(
            "/accounts",
            json={"name": "B's", "type": "checking", "currency": "USD"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    resp = await client.post(
        "/transactions",
        json=_txn(account_id, type="transfer", category_id=None, transfer_account_id=b_account["id"]),
    )
    assert resp.status_code == 404


async def test_cannot_create_a_transaction_against_another_users_category(client, account_id):
    b_tokens = await register_user(client, "txnb5@example.com")
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")

    resp = await client.post("/transactions", json=_txn(account_id, category_id=b_groceries))
    assert resp.status_code == 404


async def test_cannot_attach_another_users_tag(client, account_id):
    b_tokens = await register_user(client, "txnb6@example.com")
    b_tag = (
        await client.post("/tags", json={"name": "b-only"}, headers=auth_headers(b_tokens["access_token"]))
    ).json()

    resp = await client.post("/transactions", json=_txn(account_id, tag_ids=[b_tag["id"]]))
    assert resp.status_code == 400


async def test_cannot_split_a_transaction_into_another_users_category(client, account_id, categories):
    b_tokens = await register_user(client, "txnb7@example.com")
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")
    a_groceries = categories["Groceries"]["id"]

    resp = await client.post(
        "/transactions",
        json=_txn(
            account_id,
            amount="20.00",
            category_id=None,
            splits=[
                {"category_id": a_groceries, "amount": "10.00"},
                {"category_id": b_groceries, "amount": "10.00"},
            ],
        ),
    )
    assert resp.status_code == 404


async def test_cannot_update_a_transaction_to_reference_another_users_account(client, account_id):
    a_txn = (await client.post("/transactions", json=_txn(account_id))).json()

    b_tokens = await register_user(client, "txnb8@example.com")
    b_account = (
        await client.post(
            "/accounts",
            json={"name": "B's", "type": "checking", "currency": "USD"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    resp = await client.patch(f"/transactions/{a_txn['id']}", json={"account_id": b_account["id"]})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_transactions.py -v -k "user_a or user_b or another_user or cannot_"`
Expected: FAIL — none of these cross-references are checked yet, and the
router has no auth at all yet, so `test_user_a_cannot_see_user_bs_transaction`
would currently show both transactions to both users.

- [ ] **Step 3: Wire the router**

Modify `backend/app/api/routes/transactions.py` — this replaces the whole
file. Read the current file first (`git show HEAD:backend/app/api/routes/transactions.py`
or just open it) to confirm you're starting from the same base the diff
below assumes; the plan was written against the version already in the
repository as of Part 1's completion.

Add these imports (merge with the existing import block rather than
duplicating anything already there):

```python
from app.api.deps import get_current_user
from app.models.account import Account
from app.models.user import User
from app.services.scoped import get_owned_or_404, scoped
```

Replace `_resolve_tags`:

```python
async def _resolve_tags(session: AsyncSession, tag_ids: list[int], user_id: int) -> list[Tag]:
    if not tag_ids:
        return []
    result = await session.execute(select(Tag).where(Tag.id.in_(tag_ids), Tag.user_id == user_id))
    tags = list(result.scalars().all())
    missing = set(tag_ids) - {tag.id for tag in tags}
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown tag id(s): {sorted(missing)}")
    return tags
```

Replace `_ensure_category_matches_type`:

```python
async def _ensure_category_matches_type(
    session: AsyncSession, category_id: int | None, transaction_type: TransactionType, user_id: int
) -> Category | None:
    """A category picked for an income transaction must itself be an income
    category (and likewise for expense) — otherwise the dashboard's spending
    breakdown, which only joins EXPENSE-typed rows, would silently misclassify
    the entry. Returns the fetched category (or None for category_id=None) so
    callers that also need the row itself — _build_splits, below — don't have
    to fetch it a second time. Ownership-checked, not just existence-checked
    — a category that exists but belongs to another user is treated as not
    found (404), the same way every other cross-reference in this file is."""
    if category_id is None:
        return None
    expected_kind = _TYPE_TO_CATEGORY_KIND.get(transaction_type)
    category = await get_owned_or_404(session, Category, category_id, user_id, detail="Category not found")
    if expected_kind is not None and category.kind != expected_kind:
        raise HTTPException(
            status_code=400,
            detail=f"Category '{category.name}' is a {category.kind.value} category and cannot be used for a {transaction_type.value} transaction",
        )
    return category
```

Add a new helper right after it:

```python
async def _ensure_account_owned(session: AsyncSession, account_id: int, user_id: int) -> None:
    """Raises 404 if `account_id` doesn't exist or belongs to another user.
    Used for both `account_id` and `transfer_account_id` — a transaction
    (including its transfer destination) can only ever touch accounts the
    caller owns."""
    await get_owned_or_404(session, Account, account_id, user_id, detail="Account not found")
```

Replace `_build_splits`'s signature and its call to `_ensure_category_matches_type`:

```python
async def _build_splits(
    session: AsyncSession, splits: list[TransactionSplitInput], transaction_type: TransactionType, user_id: int
) -> list[TransactionSplit]:
    """A split's whole point is dividing one purchase's total across the
    *subcategories of one parent* (a hypermarket receipt: part groceries ->
    Sweets, part -> Alcohol) — not across unrelated top-level categories, or
    the numbers would roll up into two different parents and the "spent X on
    Groceries, split between Sweets/Alcohol" picture the feature exists for
    falls apart. Each split may point at that parent category itself (an
    unspecified-subcategory line) or at any one of its direct children —
    enforced by requiring every split's own top-level ancestor
    (parent_id, or its own id if it has none) to agree. Each split's
    category is also ownership-checked via _ensure_category_matches_type.
    """
    top_level_ids: set[int] = set()
    for split in splits:
        category = await _ensure_category_matches_type(session, split.category_id, transaction_type, user_id)
        assert category is not None  # split.category_id is required (not Optional) on the schema
        top_level_ids.add(category.parent_id if category.parent_id is not None else category.id)
    if len(top_level_ids) > 1:
        raise HTTPException(
            status_code=400,
            detail="All split categories must be the same parent category or its direct subcategories",
        )
    return [TransactionSplit(category_id=s.category_id, amount=s.amount, note=s.note) for s in splits]
```

Replace `list_transactions` — add `current_user` and scope the base query
(only the function signature and the first two lines of the body change;
every filter clause below stays exactly as it is today):

```python
@router.get("", response_model=TransactionPage)
async def list_transactions(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    account_id: int | None = None,
    category_id: int | None = None,
    tag_id: int | None = None,
    type: TransactionType | None = None,
    search: str | None = Query(default=None, min_length=1, max_length=255),
    sort: Literal["date_desc", "amount_desc", "amount_asc"] = Query(default="date_desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TransactionPage:
    stmt = scoped(select(Transaction), Transaction, current_user.id).options(*_EAGER)
    count_stmt = scoped(select(func.count()).select_from(Transaction), Transaction, current_user.id)
```

(Everything from `if year is not None:` through the `return TransactionPage(...)` at the end of this function is unchanged — leave it exactly as it is.)

Replace `list_transaction_years` — add `current_user` and scope the bounds query:

```python
@router.get("/years", response_model=list[int])
async def list_transaction_years(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> list[int]:
    """Full range of years to offer in the year picker — from the earliest
    transaction through the current year, so a gap year with no activity
    still shows up (as zero) instead of silently disappearing from the UI."""
    stmt = scoped(select(func.min(Transaction.date), func.max(Transaction.date)), Transaction, current_user.id)
    bounds = await session.execute(stmt)
    min_date, max_date = bounds.one()
    current_year = date_.today().year
    if min_date is None:
        return [current_year]
    return list(range(min_date.year, max(max_date.year, current_year) + 1))
```

Replace `create_transaction`:

```python
@router.post("", response_model=TransactionRead, status_code=201)
async def create_transaction(
    payload: TransactionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Transaction:
    await _ensure_account_owned(session, payload.account_id, current_user.id)
    if payload.transfer_account_id is not None:
        await _ensure_account_owned(session, payload.transfer_account_id, current_user.id)
    await _ensure_category_matches_type(session, payload.category_id, payload.type, current_user.id)
    fields = payload.model_dump(exclude={"tag_ids", "splits"})
    transaction = Transaction(**fields, user_id=current_user.id)
    transaction.tags = await _resolve_tags(session, payload.tag_ids, current_user.id)
    if payload.splits:
        transaction.splits = await _build_splits(session, payload.splits, payload.type, current_user.id)
    session.add(transaction)
    await session.commit()
    refreshed = await session.execute(
        select(Transaction).options(*_EAGER).where(Transaction.id == transaction.id)
    )
    return refreshed.scalar_one()
```

Replace `bulk_create_transactions`:

```python
@router.post("/bulk", response_model=TransactionBulkCreateResult, status_code=201)
async def bulk_create_transactions(
    payload: TransactionBulkCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TransactionBulkCreateResult:
    """CSV import lands here — see schemas.TransactionBulkCreate. All rows
    are validated before any is added, so a bad row 400s/404s the whole
    request instead of leaving a half-imported statement behind."""
    for item in payload.items:
        await _ensure_account_owned(session, item.account_id, current_user.id)
        if item.transfer_account_id is not None:
            await _ensure_account_owned(session, item.transfer_account_id, current_user.id)
        await _ensure_category_matches_type(session, item.category_id, item.type, current_user.id)

    transactions = []
    for item in payload.items:
        transaction = Transaction(**item.model_dump(exclude={"tag_ids", "splits"}), user_id=current_user.id)
        transaction.tags = await _resolve_tags(session, item.tag_ids, current_user.id)
        if item.splits:
            transaction.splits = await _build_splits(session, item.splits, item.type, current_user.id)
        transactions.append(transaction)

    session.add_all(transactions)
    await session.commit()
    return TransactionBulkCreateResult(created=len(transactions))
```

Replace `update_transaction` — add `current_user`, replace the initial
fetch with an owner-scoped one, and thread `current_user.id` through
every helper call. The validation logic in the middle (transfer/split
rule checks) is unchanged:

```python
@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Transaction:
    # Eager-loads tags and splits — assigning transaction.tags/splits below
    # would otherwise lazy-load the current collection first to diff
    # against, which async SQLAlchemy can't do outside an explicit await
    # (MissingGreenlet).
    result = await session.execute(
        scoped(select(Transaction), Transaction, current_user.id)
        .where(Transaction.id == transaction_id)
        .options(selectinload(Transaction.tags), selectinload(Transaction.splits))
    )
    transaction = result.scalar_one_or_none()
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    updates = payload.model_dump(exclude_unset=True, exclude={"tag_ids", "splits"})
    # Checks run against the row as it would look after the patch, not just
    # the fields sent: switching type alone can invalidate fields left
    # untouched.
    effective_type = updates.get("type", transaction.type)
    effective_category_id = updates.get("category_id", transaction.category_id)
    effective_account_id = updates.get("account_id", transaction.account_id)
    effective_transfer_account_id = updates.get("transfer_account_id", transaction.transfer_account_id)
    effective_amount = updates.get("amount", transaction.amount)

    if "account_id" in updates:
        await _ensure_account_owned(session, updates["account_id"], current_user.id)
    if "transfer_account_id" in updates and updates["transfer_account_id"] is not None:
        await _ensure_account_owned(session, updates["transfer_account_id"], current_user.id)
    await _ensure_category_matches_type(session, effective_category_id, effective_type, current_user.id)
    violation = transfer_rule_violation(
        type=effective_type,
        account_id=effective_account_id,
        transfer_account_id=effective_transfer_account_id,
        category_id=effective_category_id,
    )
    if violation:
        raise HTTPException(status_code=400, detail=violation)

    if payload.splits is not None:
        split_count = len(payload.splits)
        split_total = sum((s.amount for s in payload.splits), Decimal("0")) if payload.splits else None
    else:
        # Splits weren't touched by this patch — check the existing rows as
        # they stand. Reading straight off the ORM objects here (not
        # rebuilding TransactionSplitInput) on purpose: an existing split's
        # category_id can be None if that category was since deleted, and
        # the sum check below needs none of that — only tags/category
        # values that were actually just fetched from the caller could ever
        # need to be re-validated, and those go through payload.splits above.
        split_count = len(transaction.splits)
        split_total = sum((s.amount for s in transaction.splits), Decimal("0")) if transaction.splits else None
    split_violation = split_rule_violation(
        type=effective_type,
        amount=effective_amount,
        category_id=effective_category_id,
        split_count=split_count,
        split_total=split_total,
    )
    if split_violation:
        raise HTTPException(status_code=400, detail=split_violation)

    for field, value in updates.items():
        setattr(transaction, field, value)
    if payload.tag_ids is not None:
        transaction.tags = await _resolve_tags(session, payload.tag_ids, current_user.id)
    if payload.splits is not None:
        transaction.splits = await _build_splits(session, payload.splits, effective_type, current_user.id)
    await session.commit()
    refreshed = await session.execute(
        select(Transaction).options(*_EAGER).where(Transaction.id == transaction_id)
    )
    return refreshed.scalar_one()
```

Replace `delete_transaction`:

```python
@router.delete("/{transaction_id}", status_code=204)
async def delete_transaction(
    transaction_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    transaction = await get_owned_or_404(session, Transaction, transaction_id, current_user.id, detail="Transaction not found")
    await session.delete(transaction)
    await session.commit()
```

- [ ] **Step 4: Run the new isolation tests**

Run: `docker compose exec backend pytest tests/test_transactions.py -v`
Expected: PASS — every test in the file, old and new. If any of the
~50 pre-existing tests in this file fail, read the failure carefully:
the most likely cause is a pre-existing test that creates a transaction
against an account/category from a *different* client/fixture context
than the one it later reads with — since this router is now
authenticated and scoped, such a test would need `account_id`/
`categories` sourced from the same authenticated session it later reads
from (this should already be the case throughout the existing file, since
both come from the same `client`-fixture-backed fixtures, but double
check if something fails).

- [ ] **Step 5: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS, except the one known pre-existing `test_backup.py`
failure — unchanged from before this task.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/transactions.py backend/tests/test_transactions.py
git commit -m "Изолировать transactions по пользователю, включая проверку владения всех перекрёстных ссылок"
```

---

## Plan Self-Review Notes

- **Spec coverage:** Implements the "Authorization / data isolation"
  section's chosen approach for `transactions`, and closes the specific
  cross-reference gap Part 1's final review identified (account_id/
  category_id/tag_ids/transfer_account_id ownership) — this was
  explicitly named in Part 1's ledger as "the class of gap Part 2 exists
  to close comprehensively."
- **Type/interface consistency:** `_ensure_category_matches_type`,
  `_resolve_tags`, `_build_splits`, `_ensure_account_owned` all take a
  `user_id: int` parameter with the same name/position convention used
  throughout Part 1's service functions. `scoped()`/`get_owned_or_404()`
  imports and call shapes match Part 1's usage exactly.
- **No placeholders:** every step contains complete, real code.

---

## Next Plan

**Part 2B (assets + crypto):** adds `user_id` to `assets`,
`asset_valuations`, `crypto_portfolios`, `crypto_holdings`,
`crypto_transactions` (`crypto_portfolios` was missing from the original
spec's table list — a gap noted during Part 1's brainstorming, now
in scope here); wires `routes/assets.py` and `routes/crypto.py`; adds
the CoinGecko price-cache layer from the spec. Assets and crypto are
grouped together because `CryptoHolding` is a 1:1 extension of `Asset`
(shares its primary key) — converting one without the other would leave
the pair in an inconsistent state.

**Part 3 (read-only aggregation + cutover):** wires `dashboard`,
`net_worth`, `cash_flow`, `reports`, `advice`, and finishes converting
the remaining unscoped signals in `insights` (four were left unscoped by
Part 1 pending Transaction/Account being fully isolated — now that this
plan closes Transactions, Part 3 should re-check whether
`_negative_cash_flow_streak`/`_idle_cash_account_count` can finally be
scoped too); reworks `backup_service.py` to be fully per-user (both the
"invisible restored rows" issue found in Part 1 and the "wipes
everyone's data" issue stopgapped in Part 1's Task 6.5); runs the final
migration flipping every `user_id` column added across Part 1, 2A, and
2B to `NOT NULL`; retires `AURUM_BASIC_AUTH_USER`/`PASSWORD` and nginx's
`auth_basic` (coordinated with whichever plan adds real frontend login
screens).
