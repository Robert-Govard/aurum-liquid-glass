# Admin Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the app owner a UI to list all registered users, see their per-user statistics (activity + current net worth), and manage them (enable/disable, delete) — on top of a backend admin API that already exists and is already fully tested.

**Architecture:** The backend (`/api/admin/users` GET/PATCH/DELETE, `is_admin`/`is_active` on `User`, `get_current_admin` auth dependency) was built in an earlier plan and needs only two additions: a `last_login_at` timestamp and a batched per-user stats aggregation (accounts/transactions count + current net worth, computed for ALL users in a handful of queries, never one query per user). The frontend is entirely new: an `AdminPage` reusing existing UI primitives (`Card`, `Switch`, `Dialog`/`GroupedList` are NOT needed here — this is a plain list, not a picker), gated behind `is_admin` both in navigation visibility and (defensively) in the page itself.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic (backend), React 19 + React Query + react-router-dom v7 + Tailwind v4 (frontend). No frontend test framework exists (confirmed: no vitest/jest, no `.test.ts(x)` files anywhere) — frontend verification is `npm run build` plus code reading. Backend has a full pytest suite (`httpx.AsyncClient` against the FastAPI app) — new backend code gets real tests.

**Spec:** `docs/superpowers/specs/2026-09-11-admin-panel-design.md`

## Global Constraints

- `PATCH`/`DELETE /api/admin/users/{id}` keep their current response shape (`UserRead`, no stats) — only `GET /api/admin/users` gains stats fields, via a new `AdminUserRead` schema.
- `/api/auth/me` must NOT gain any new fields — it keeps using plain `UserRead`.
- Stats are computed batched (a handful of aggregate SQL queries across ALL users), never in a per-user loop.
- Delete confirmation is a plain `window.confirm`, matching every other destructive action in this app (accounts, categories, etc.) — no stronger confirmation UX.
- An admin can never disable or delete their own account, via the API (400) or the UI (buttons don't render on their own row).
- Every user-visible frontend string goes through `frontend/src/lib/i18n.ts`, added to both `ru` and `en` blocks in the same commit.
- Backend service-layer error messages (`HTTPException(detail=...)`) are in English, matching every existing message in `user_service.py`/`auth_service.py` — these are not user-facing strings and don't go through `lib/i18n.ts` (that mechanism is frontend-only).
- No visual/device verification is possible in this environment — every task's testing section says so explicitly rather than claiming it was checked visually.

---

### Task 1: Track `last_login_at`

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/alembic/versions/<generated>_add_last_login_at_to_users.py`
- Modify: `backend/app/services/auth_service.py`
- Test: `backend/tests/test_auth.py` (or wherever existing login/register tests live — see Step 5)

**Interfaces:**
- Produces: `User.last_login_at: datetime | None` — consumed by Task 2's `AdminUserRead` schema.

- [ ] **Step 1: Add the column to the model**

In `backend/app/models/user.py`, the class currently ends with:

```python
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Change to:

```python
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set by auth_service.login()/register() — NULL means "never logged in
    # since this column was added" for pre-existing users, or genuinely
    # never (registered but never came back). Not touched by
    # auth_service.refresh() — that's a silent session renewal, not an
    # explicit login event.
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: Create the migration**

Run: `cd backend && alembic revision -m "add last_login_at to users"`

This prints the path of a new file under `alembic/versions/`, pre-filled with a fresh `revision` id and `down_revision` (Alembic auto-detects the current head, `43a4507fff95`). Open that generated file and replace its `upgrade`/`downgrade` functions (leave the auto-generated `revision`/`down_revision`/`branch_labels`/`depends_on` lines exactly as generated) with:

```python
def upgrade() -> None:
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'last_login_at')
```

(No server-side default/backfill needed — this is a nullable column, so adding it to a table with existing rows is safe as-is, unlike the `risk_level` migration you might see elsewhere in this same directory which needed a temporary default for a NOT NULL column.)

- [ ] **Step 3: Set `last_login_at` in `login()` and `register()`**

In `backend/app/services/auth_service.py`, `register()` currently reads:

```python
async def register(session: AsyncSession, payload: RegisterRequest) -> TokenPair:
    existing = await session.execute(select(User.id).where(User.email == payload.email))
    if existing.first() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    await session.flush()  # assigns user.id without ending the transaction

    await seed_default_categories(session, user.id)
    await seed_default_app_settings(session, user.id)

    return await _issue_token_pair(session, user.id)
```

Change to (a fresh registration counts as the first login — otherwise a brand-new user would show as "never logged in" in the admin panel until they log in a second time, which is misleading):

```python
async def register(session: AsyncSession, payload: RegisterRequest) -> TokenPair:
    existing = await session.execute(select(User.id).where(User.email == payload.email))
    if existing.first() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password), last_login_at=datetime.now(timezone.utc))
    session.add(user)
    await session.flush()  # assigns user.id without ending the transaction

    await seed_default_categories(session, user.id)
    await seed_default_app_settings(session, user.id)

    return await _issue_token_pair(session, user.id)
```

`login()` currently reads:

```python
async def login(session: AsyncSession, email: str, password: str) -> TokenPair:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return await _issue_token_pair(session, user.id)
```

Change to:

```python
async def login(session: AsyncSession, email: str, password: str) -> TokenPair:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    user.last_login_at = datetime.now(timezone.utc)
    return await _issue_token_pair(session, user.id)
```

Both mutations get committed by `_issue_token_pair`'s own `await session.commit()` right after — no separate commit needed here.

- [ ] **Step 4: Run the backend test suite**

Run: `cd backend && python -m pytest -q`
Expected: all existing tests still pass (this is an additive nullable column and two new field assignments — no existing behavior changed).

- [ ] **Step 5: Add a regression test**

Find the existing test file that covers `register()`/`login()` (likely `backend/tests/test_auth.py` — check with `grep -rl "def test_.*register\|def test_.*login" backend/tests/`). Add:

```python
async def test_login_and_register_set_last_login_at(client, test_sessionmaker):
    from sqlalchemy import select
    from app.models.user import User

    resp = await client.post("/auth/register", json={"email": "lastlogin@example.com", "password": "hunter22"})
    assert resp.status_code == 200

    async with test_sessionmaker() as session:
        result = await session.execute(select(User).where(User.email == "lastlogin@example.com"))
        user = result.scalar_one()
        assert user.last_login_at is not None
        first_login = user.last_login_at

    login_resp = await client.post("/auth/login", json={"email": "lastlogin@example.com", "password": "hunter22"})
    assert login_resp.status_code == 200

    async with test_sessionmaker() as session:
        result = await session.execute(select(User).where(User.email == "lastlogin@example.com"))
        user = result.scalar_one()
        assert user.last_login_at is not None
        assert user.last_login_at >= first_login
```

Place it in whichever existing auth test file you found — match that file's existing import style at the top rather than the inline imports shown above if the file already imports `select`/`User` at module level.

- [ ] **Step 6: Run the new test**

Run: `cd backend && python -m pytest -q -k last_login_at`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/models/user.py app/services/auth_service.py alembic/versions/*_add_last_login_at_to_users.py tests/
git commit -m "Записывать last_login_at при входе и регистрации"
```

---

### Task 2: Batched per-user stats, `AdminUserRead`, self-lockout guard

**Files:**
- Create: `backend/app/services/admin_stats_service.py`
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/services/user_service.py`
- Modify: `backend/app/api/routes/admin.py`
- Test: `backend/tests/test_admin.py`

**Interfaces:**
- Consumes: `User.last_login_at` (Task 1).
- Produces: `AdminUserRead` schema (from `app.schemas.user`) with fields `id, email, is_admin, is_active, created_at, last_login_at, accounts_count, transactions_count, net_worth` — consumed by Task 3's frontend `AdminUser` type (field names must match exactly, since the frontend types this response shape by hand, not via codegen).
- Produces: `get_user_stats(session) -> dict[int, UserStats]` and `UserStats` (fields `accounts_count: int`, `transactions_count: int`, `net_worth: Decimal`) from `app.services.admin_stats_service`.
- Produces: `update_user(session, user_id, payload, acting_admin_id)` and `delete_user(session, user_id, acting_admin_id)` — both raise `HTTPException(400, "Cannot modify your own account")` when `user_id == acting_admin_id`.

- [ ] **Step 1: Create the batched stats service**

Create `backend/app/services/admin_stats_service.py`:

```python
"""Per-user aggregate statistics for the admin user list. Batched across
ALL users in a handful of queries — the whole point of this module is that
computing net worth one user at a time (the way
net_worth_service.get_net_worth_summary() does, for a single user's full
history chart) would mean a query storm proportional to user count for a
list that shows every user at once."""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.asset import Asset, AssetValuation
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.services.net_worth_service import CASH_ACCOUNT_TYPES


@dataclass
class UserStats:
    accounts_count: int = 0
    transactions_count: int = 0
    net_worth: Decimal = field(default_factory=lambda: Decimal("0"))


async def get_user_stats(session: AsyncSession) -> dict[int, UserStats]:
    stats: dict[int, UserStats] = defaultdict(UserStats)

    accounts_result = await session.execute(select(Account.user_id, func.count(Account.id)).group_by(Account.user_id))
    for user_id, count in accounts_result.all():
        stats[user_id].accounts_count = count

    transactions_result = await session.execute(
        select(Transaction.user_id, func.count(Transaction.id)).group_by(Transaction.user_id)
    )
    for user_id, count in transactions_result.all():
        stats[user_id].transactions_count = count

    cash_by_user = await _cash_totals_by_user(session)
    asset_by_user = await _asset_totals_by_user(session)
    for user_id in set(cash_by_user) | set(asset_by_user):
        stats[user_id].net_worth = cash_by_user.get(user_id, Decimal("0")) + asset_by_user.get(user_id, Decimal("0"))

    return dict(stats)


async def _cash_totals_by_user(session: AsyncSession) -> dict[int, Decimal]:
    """Same rule as net_worth_service._cash_cumulative_events (reuses its
    CASH_ACCOUNT_TYPES constant so the definition of "cash" can't drift
    between the two), but as one lifetime total per user instead of a
    per-user daily series — this is for a list of totals, not a chart."""
    accounts_result = await session.execute(select(Account.id, Account.user_id, Account.type))
    cash_account_owner: dict[int, int] = {}
    for account_id, user_id, account_type in accounts_result.all():
        if account_type in CASH_ACCOUNT_TYPES:
            cash_account_owner[account_id] = user_id

    if not cash_account_owner:
        return {}

    txns_result = await session.execute(
        select(Transaction.type, Transaction.amount, Transaction.account_id, Transaction.transfer_account_id)
    )

    totals: dict[int, Decimal] = defaultdict(Decimal)
    for tx_type, amount, account_id, transfer_account_id in txns_result.all():
        if tx_type == TransactionType.INCOME and account_id in cash_account_owner:
            totals[cash_account_owner[account_id]] += amount
        elif tx_type == TransactionType.EXPENSE and account_id in cash_account_owner:
            totals[cash_account_owner[account_id]] -= amount
        elif tx_type == TransactionType.TRANSFER:
            if account_id in cash_account_owner:
                totals[cash_account_owner[account_id]] -= amount
            # transfer_account_id always belongs to the same user as
            # account_id (enforced at write time — see
            # net_worth_service.py's own comment on this same invariant),
            # so cash_account_owner[transfer_account_id] is never a
            # different user than cash_account_owner[account_id].
            if transfer_account_id is not None and transfer_account_id in cash_account_owner:
                totals[cash_account_owner[transfer_account_id]] += amount
    return dict(totals)


async def _asset_totals_by_user(session: AsyncSession) -> dict[int, Decimal]:
    """Latest AssetValuation per asset, summed per owning user — the
    cross-user equivalent of net_worth_service._asset_events_and_class_totals's
    current_by_asset, computed with a window function instead of a
    groupby-after-order-by (that trick works per single user; here we want
    one query across every user's assets at once)."""
    latest = (
        select(
            AssetValuation.asset_id,
            AssetValuation.value,
            func.row_number()
            .over(partition_by=AssetValuation.asset_id, order_by=AssetValuation.as_of_date.desc())
            .label("rn"),
        )
    ).subquery()

    result = await session.execute(
        select(Asset.user_id, latest.c.value).join(latest, latest.c.asset_id == Asset.id).where(latest.c.rn == 1)
    )
    totals: dict[int, Decimal] = defaultdict(Decimal)
    for user_id, value in result.all():
        totals[user_id] += value
    return dict(totals)
```

- [ ] **Step 2: Add `AdminUserRead` schema**

In `backend/app/schemas/user.py`, currently:

```python
"""Response/request shapes for /api/admin/users — never include
password_hash, deliberately."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    is_active: bool
```

Change to:

```python
"""Response/request shapes for /api/admin/users — never include
password_hash, deliberately."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    is_active: bool


class AdminUserRead(UserRead):
    """GET /api/admin/users only — /api/auth/me keeps using plain UserRead,
    deliberately never exposing these per-user stats about "yourself" via
    that shape (the normal dashboard is where a user sees their own
    numbers)."""

    last_login_at: datetime | None
    accounts_count: int
    transactions_count: int
    net_worth: Decimal
```

- [ ] **Step 3: Update `user_service.py`**

Replace the full contents of `backend/app/services/user_service.py` with:

```python
"""Admin operations on User rows — list/disable/delete. No self-service
"become admin" path exists by design; see scripts/promote_admin.py for how
the first admin is created."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import AdminUserRead, UserUpdate
from app.services.admin_stats_service import UserStats, get_user_stats


async def list_users(session: AsyncSession) -> list[AdminUserRead]:
    result = await session.execute(select(User).order_by(User.created_at))
    users = list(result.scalars().all())
    stats = await get_user_stats(session)
    empty_stats = UserStats()
    return [
        AdminUserRead(
            id=user.id,
            email=user.email,
            is_admin=user.is_admin,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            accounts_count=stats.get(user.id, empty_stats).accounts_count,
            transactions_count=stats.get(user.id, empty_stats).transactions_count,
            net_worth=stats.get(user.id, empty_stats).net_worth,
        )
        for user in users
    ]


async def update_user(session: AsyncSession, user_id: int, payload: UserUpdate, acting_admin_id: int) -> User:
    if user_id == acting_admin_id:
        raise HTTPException(status_code=400, detail="Cannot modify your own account")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Only a True -> False transition should touch tokens: re-enabling a user
    # shouldn't hand back their old sessions, and re-saving an already
    # disabled user shouldn't re-run this (harmless, but pointless) query.
    is_disabling = user.is_active and not payload.is_active
    user.is_active = payload.is_active
    if is_disabling:
        # Disabling a user should kill their live sessions immediately, not
        # just rely on auth_service.refresh()'s own is_active check to reject
        # them lazily on next use — an admin disabling someone expects it to
        # take effect now. Same revoke-in-place pattern as auth_service's
        # logout().
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user_id: int, acting_admin_id: int) -> None:
    if user_id == acting_admin_id:
        raise HTTPException(status_code=400, detail="Cannot modify your own account")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()
```

- [ ] **Step 4: Update `routes/admin.py`**

Replace the full contents of `backend/app/api/routes/admin.py` with:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_session
from app.models.user import User
from app.schemas.user import AdminUserRead, UserRead, UserUpdate
from app.services.user_service import delete_user, list_users, update_user

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/users", response_model=list[AdminUserRead])
async def list_users_route(session: AsyncSession = Depends(get_session)) -> list[AdminUserRead]:
    return await list_users(session)


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user_route(
    user_id: int,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    current_admin: User = Depends(get_current_admin),
) -> User:
    return await update_user(session, user_id, payload, current_admin.id)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user_route(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    current_admin: User = Depends(get_current_admin),
) -> None:
    await delete_user(session, user_id, current_admin.id)
```

(`current_admin: User = Depends(get_current_admin)` is added as an explicit parameter on the two routes that need the acting admin's id — FastAPI caches dependency results per-request, so this doesn't run `get_current_admin` twice even though the router already depends on it at the router level for the 403 gate.)

- [ ] **Step 5: Run the existing test suite**

Run: `cd backend && python -m pytest -q`
Expected: all pass, including the existing 5 tests in `test_admin.py` (their assertions check specific keys/values, not an exact key set — the new stats fields are additive and don't break them).

- [ ] **Step 6: Add new tests to `test_admin.py`**

Add `from decimal import Decimal` to the top of `backend/tests/test_admin.py` if not already imported, then add:

```python
async def test_admin_cannot_disable_own_account(client, test_sessionmaker):
    admin_tokens = await _register(client, "selflock1@example.com")
    await _make_admin(test_sessionmaker, "selflock1@example.com")

    users = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    own_id = next(u["id"] for u in users if u["email"] == "selflock1@example.com")

    resp = await client.patch(
        f"/admin/users/{own_id}", json={"is_active": False}, headers=_auth(admin_tokens["access_token"])
    )
    assert resp.status_code == 400


async def test_admin_cannot_delete_own_account(client, test_sessionmaker):
    admin_tokens = await _register(client, "selflock2@example.com")
    await _make_admin(test_sessionmaker, "selflock2@example.com")

    users = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    own_id = next(u["id"] for u in users if u["email"] == "selflock2@example.com")

    resp = await client.delete(f"/admin/users/{own_id}", headers=_auth(admin_tokens["access_token"]))
    assert resp.status_code == 400


async def test_admin_list_includes_per_user_stats(client, test_sessionmaker):
    admin_tokens = await _register(client, "statsadmin@example.com")
    await _make_admin(test_sessionmaker, "statsadmin@example.com")

    target_tokens = await _register(client, "statstarget@example.com")
    target_account = (
        await client.post(
            "/accounts",
            json={"name": "Target Wallet", "type": "checking", "currency": "USD"},
            headers=_auth(target_tokens["access_token"]),
        )
    ).json()
    target_categories = (await client.get("/categories", headers=_auth(target_tokens["access_token"]))).json()
    salary_id = next(c["id"] for c in target_categories if c["name"] == "Salary")
    await client.post(
        "/transactions",
        json={
            "account_id": target_account["id"],
            "type": "income",
            "amount": "500.00",
            "description": "salary",
            "date": "2026-01-15",
            "category_id": salary_id,
        },
        headers=_auth(target_tokens["access_token"]),
    )

    users = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    target = next(u for u in users if u["email"] == "statstarget@example.com")
    assert target["accounts_count"] == 1
    assert target["transactions_count"] == 1
    assert Decimal(str(target["net_worth"])) == Decimal("500.00")

    # A user with zero accounts/transactions/assets still gets zeroed
    # stats, not a missing key or a crash — and critically, does NOT show
    # statstarget's 500.00 (the thing a batched cross-user query could get
    # wrong: mixing sums between users).
    admin_self = next(u for u in users if u["email"] == "statsadmin@example.com")
    assert admin_self["accounts_count"] == 0
    assert admin_self["transactions_count"] == 0
    assert Decimal(str(admin_self["net_worth"])) == Decimal("0")
```

- [ ] **Step 7: Run the new tests**

Run: `cd backend && python -m pytest -q -k "own_account or per_user_stats"`
Expected: 3 PASS.

- [ ] **Step 8: Run the full suite once more**

Run: `cd backend && python -m pytest -q`
Expected: all pass (no regressions from Steps 3-4's rewrite of `user_service.py`/`routes/admin.py`).

- [ ] **Step 9: Commit**

```bash
cd backend
git add app/services/admin_stats_service.py app/schemas/user.py app/services/user_service.py app/api/routes/admin.py tests/test_admin.py
git commit -m "Добавить статистику по пользователям и защиту от самоблокировки в админку"
```

---

### Task 3: Frontend — the Admin page itself

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/format.ts`
- Create: `frontend/src/api/admin.ts`
- Create: `frontend/src/hooks/useAdmin.ts`
- Create: `frontend/src/components/admin/AdminUserList.tsx`
- Create: `frontend/src/pages/AdminPage.tsx`
- Modify: `frontend/src/lib/i18n.ts`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `AdminUserRead`'s exact field names from Task 2 (`id, email, is_admin, is_active, created_at, last_login_at, accounts_count, transactions_count, net_worth`) — the frontend `AdminUser` type below must match these names exactly, field for field.
- Produces: `AdminUser` type (from `@/types`), `fetchAdminUsers/updateAdminUser/deleteAdminUser` (from `@/api/admin`), `useAdminUsers/useUpdateAdminUser/useDeleteAdminUser` (from `@/hooks/useAdmin`), `AdminUserList` component, `AdminPage` component — the last is consumed by Task 4's `NAV_ITEMS`/route wiring is already done in THIS task (Task 4 only adds nav visibility, not the route — see Step 8 below).

- [ ] **Step 1: Add the `AdminUser` type**

In `frontend/src/types/index.ts`, add (anywhere in the file, alongside the other interfaces — e.g. right after the `Account`-related types):

```ts
export interface AdminUser {
  id: number;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  accounts_count: number;
  transactions_count: number;
  net_worth: string;
}
```

- [ ] **Step 2: Add a full-date formatter**

In `frontend/src/lib/format.ts`, `formatTransactionDate` takes a date-ONLY string and appends `T00:00:00` itself — not usable for a full ISO timestamp (`created_at`/`last_login_at` arrive as full datetimes). Add a new function right after `formatTransactionDate`:

```ts
/** Full date for admin-only contexts (registration date, last login) —
 * unlike formatTransactionDate, takes a full ISO datetime (already has a
 * time component), not a date-only string. */
export function formatDateTime(isoDateTime: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(isoDateTime));
}
```

- [ ] **Step 3: Create the API module**

Create `frontend/src/api/admin.ts`:

```ts
import { api } from "@/api/client";
import type { AdminUser } from "@/types";

export function fetchAdminUsers() {
  return api.get<AdminUser[]>("/admin/users");
}

export function updateAdminUser(id: number, input: { is_active: boolean }) {
  return api.patch<AdminUser>(`/admin/users/${id}`, input);
}

export function deleteAdminUser(id: number) {
  return api.delete<void>(`/admin/users/${id}`);
}
```

(`updateAdminUser`'s real backend response is the narrower `UserRead` shape, not the full `AdminUser`/`AdminUserRead` with stats — per Global Constraints, `PATCH` doesn't return stats. Typing it as `AdminUser` here is a harmless over-approximation on the frontend side: the mutation's result isn't read for its stats fields anywhere in this plan, only used to trigger a refetch of the list — see Step 4.)

- [ ] **Step 4: Create the React Query hooks**

Create `frontend/src/hooks/useAdmin.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteAdminUser, fetchAdminUsers, updateAdminUser } from "@/api/admin";

export function useAdminUsers() {
  return useQuery({ queryKey: ["admin-users"], queryFn: fetchAdminUsers });
}

export function useUpdateAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) => updateAdminUser(id, { is_active: isActive }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

export function useDeleteAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteAdminUser(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}
```

- [ ] **Step 5: Add i18n keys**

In `frontend/src/lib/i18n.ts`, the `ru` block currently has (around line 21-22):

```ts
  "nav.settings": "Настройки",
  "nav.more": "Ещё",
```

Change to:

```ts
  "nav.settings": "Настройки",
  "nav.admin": "Админка",
  "nav.more": "Ещё",
```

The `en` block has the matching pair (around line 531-532):

```ts
  "nav.settings": "Settings",
  "nav.more": "More",
```

Change to:

```ts
  "nav.settings": "Settings",
  "nav.admin": "Admin",
  "nav.more": "More",
```

Then, in the `ru` block, right after `"common.select": "Выбрать",` (around line 46), add a new group:

```ts
  "common.select": "Выбрать",

  "admin.empty": "Пользователей пока нет.",
  "admin.adminBadge": "админ",
  "admin.disabledBadge": "отключён",
  "admin.registeredOn": "Регистрация: {{date}}",
  "admin.lastLoginOn": "Последний вход: {{date}}",
  "admin.neverLoggedIn": "Ещё не входил",
  "admin.netWorthLabel": "Капитал: {{amount}}",
  "admin.disable": "Отключить",
  "admin.enable": "Включить",
  "admin.confirmDelete": "Удалить пользователя {{email}} и все его данные? Это необратимо.",
  "admin.loadError": "Не удалось загрузить список пользователей.",
```

And in the `en` block, right after `"common.select": "Select",` (around line 556):

```ts
  "common.select": "Select",

  "admin.empty": "No users yet.",
  "admin.adminBadge": "admin",
  "admin.disabledBadge": "disabled",
  "admin.registeredOn": "Registered: {{date}}",
  "admin.lastLoginOn": "Last login: {{date}}",
  "admin.neverLoggedIn": "Never logged in",
  "admin.netWorthLabel": "Net worth: {{amount}}",
  "admin.disable": "Disable",
  "admin.enable": "Enable",
  "admin.confirmDelete": "Delete user {{email}} and all their data? This cannot be undone.",
  "admin.loadError": "Failed to load the user list.",
```

- [ ] **Step 6: Run the build to catch any i18n key mismatch**

Run: `cd frontend && npm run build`
Expected: succeeds (the `en` block is typed as `Record<keyof typeof ru, string>`, so a key present in only one block fails the build here).

- [ ] **Step 7: Create the user list component**

Create `frontend/src/components/admin/AdminUserList.tsx`:

```tsx
import { Trash2 } from "lucide-react";
import { Switch } from "@/components/ui/Switch";
import { formatCurrency, formatDateTime, pluralizeRu } from "@/lib/format";
import { useTranslation, type Language } from "@/lib/i18n";
import type { AdminUser } from "@/types";

interface AdminUserListProps {
  items: AdminUser[];
  currentUserId: number | undefined;
  onToggleActive: (user: AdminUser) => void;
  onDelete: (user: AdminUser) => void;
}

function accountsCountLabel(count: number, language: Language): string {
  if (language === "ru") return pluralizeRu(count, "счёт", "счёта", "счетов");
  return count === 1 ? "account" : "accounts";
}

function transactionsCountLabel(count: number, language: Language): string {
  if (language === "ru") return pluralizeRu(count, "транзакция", "транзакции", "транзакций");
  return count === 1 ? "transaction" : "transactions";
}

export function AdminUserList({ items, currentUserId, onToggleActive, onDelete }: AdminUserListProps) {
  const { t, language } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("admin.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((user) => {
        const isSelf = user.id === currentUserId;
        return (
          <li key={user.id} className={`flex flex-wrap items-center gap-3 py-3 ${!user.is_active ? "opacity-50" : ""}`}>
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-text-primary">
                <span className="truncate">{user.email}</span>
                {user.is_admin && (
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none text-text-muted">
                    {t("admin.adminBadge")}
                  </span>
                )}
                {!user.is_active && (
                  <span className="shrink-0 rounded bg-danger/10 px-1 py-0.5 text-[10px] leading-none text-danger">
                    {t("admin.disabledBadge")}
                  </span>
                )}
              </span>
              <span className="block text-xs text-text-muted">
                {t("admin.registeredOn", { date: formatDateTime(user.created_at) })}
                {" · "}
                {user.last_login_at
                  ? t("admin.lastLoginOn", { date: formatDateTime(user.last_login_at) })
                  : t("admin.neverLoggedIn")}
              </span>
              <span className="block text-xs text-text-muted">
                {user.accounts_count} {accountsCountLabel(user.accounts_count, language)}
                {", "}
                {user.transactions_count} {transactionsCountLabel(user.transactions_count, language)}
                {" · "}
                {t("admin.netWorthLabel", { amount: formatCurrency(user.net_worth) })}
              </span>
            </span>
            {!isSelf && (
              <span className="flex shrink-0 items-center gap-3">
                <Switch
                  checked={user.is_active}
                  onChange={() => onToggleActive(user)}
                  aria-label={user.is_active ? t("admin.disable") : t("admin.enable")}
                />
                <button
                  type="button"
                  onClick={() => onDelete(user)}
                  aria-label={t("common.delete")}
                  className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                >
                  <Trash2 size={16} />
                </button>
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 8: Create the page and wire its route**

Create `frontend/src/pages/AdminPage.tsx`:

```tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { AdminUserList } from "@/components/admin/AdminUserList";
import { useAdminUsers, useDeleteAdminUser, useUpdateAdminUser } from "@/hooks/useAdmin";
import { useAuthState } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";
import type { AdminUser } from "@/types";

export function AdminPage() {
  const { t } = useTranslation();
  const { user: currentUser } = useAuthState();
  const { data: users, isLoading, isError } = useAdminUsers();
  const updateUser = useUpdateAdminUser();
  const deleteUser = useDeleteAdminUser();

  function handleToggleActive(user: AdminUser) {
    updateUser.mutate({ id: user.id, isActive: !user.is_active });
  }

  function handleDelete(user: AdminUser) {
    if (window.confirm(t("admin.confirmDelete", { email: user.email }))) {
      deleteUser.mutate(user.id);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("nav.admin")}</CardTitle>
        </CardHeader>
        <CardContent>
          {isError ? (
            <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
              {t("admin.loadError")}
            </p>
          ) : isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <AdminUserList
              items={users ?? []}
              currentUserId={currentUser?.id}
              onToggleActive={handleToggleActive}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

(The `isError` branch is defense in depth for a non-admin who navigates to `/admin` directly by URL before Task 4 adds nav visibility gating — the backend's `get_current_admin` dependency is the actual security boundary, already fully tested in Task 2; this is purely so such a visit shows a clean error instead of an infinite loading spinner or an unhandled promise rejection.)

In `frontend/src/App.tsx`, add the import (alphabetically, among the other page imports):

```tsx
import { AccountsPage } from "@/pages/AccountsPage";
import { AdminPage } from "@/pages/AdminPage";
import { AdvicePage } from "@/pages/AdvicePage";
```

And add a new route — the current route list ends with:

```tsx
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
```

Change to:

```tsx
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Routes>
```

- [ ] **Step 9: Run the build**

Run: `cd frontend && npm run build`
Expected: succeeds with no new errors.

- [ ] **Step 10: Commit**

```bash
cd frontend
git add src/types/index.ts src/lib/format.ts src/api/admin.ts src/hooks/useAdmin.ts src/components/admin/AdminUserList.tsx src/pages/AdminPage.tsx src/lib/i18n.ts src/App.tsx
git commit -m "Добавить страницу админ-панели"
```

---

### Task 4: Frontend — navigation visibility

**Files:**
- Modify: `frontend/src/lib/navigation.ts`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/components/layout/MobileTabBar.tsx`

**Interfaces:**
- Consumes: `AdminPage`'s route at `/admin` (Task 3, already wired into `App.tsx`); `useAuthState()` from `@/lib/auth` (pre-existing, already used by `Topbar.tsx` the same way — returns `{ user, accessToken }` where `user: CurrentUser | null` has an `is_admin: boolean` field).
- Produces: `NavItem.adminOnly?: boolean` — the only new public surface, consumed by both `Sidebar.tsx` and `MobileTabBar.tsx` in this same task.

- [ ] **Step 1: Add `adminOnly` to `NavItem` and the nav entry**

In `frontend/src/lib/navigation.ts`, the icon imports currently are:

```ts
import {
  Activity,
  ArrowLeftRight,
  Calculator,
  Coins,
  Flag,
  Layers,
  Lightbulb,
  LayoutDashboard,
  PieChart,
  Repeat,
  Settings,
  Tags,
  Target,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
```

Change to (adding `ShieldCheck`, alphabetically):

```ts
import {
  Activity,
  ArrowLeftRight,
  Calculator,
  Coins,
  Flag,
  Layers,
  Lightbulb,
  LayoutDashboard,
  PieChart,
  Repeat,
  Settings,
  ShieldCheck,
  Tags,
  Target,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
```

The `NavItem` interface currently is:

```ts
export interface NavItem {
  labelKey: TranslationKey;
  to: string;
  icon: LucideIcon;
  disabled?: boolean;
}
```

Change to:

```ts
export interface NavItem {
  labelKey: TranslationKey;
  to: string;
  icon: LucideIcon;
  disabled?: boolean;
  // Only rendered in Sidebar.tsx/MobileTabBar.tsx when the current user's
  // is_admin is true — both filter NAV_ITEMS on this before rendering.
  adminOnly?: boolean;
}
```

`NAV_ITEMS` currently ends with:

```ts
  { labelKey: "nav.settings", to: "/settings", icon: Settings },
];
```

Change to:

```ts
  { labelKey: "nav.settings", to: "/settings", icon: Settings },
  { labelKey: "nav.admin", to: "/admin", icon: ShieldCheck, adminOnly: true },
];
```

- [ ] **Step 2: Filter in `Sidebar.tsx`**

In `frontend/src/components/layout/Sidebar.tsx`, the imports currently are:

```tsx
import { NavLink } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Logo } from "@/components/layout/Logo";
import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
```

Change to:

```tsx
import { NavLink } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Logo } from "@/components/layout/Logo";
import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { useAuthState } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
```

`NavList` currently is:

```tsx
function NavList({ collapsed }: NavListProps) {
  const { t } = useTranslation();

  return (
    <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2.5 py-2">
      {NAV_ITEMS.map((item) => {
```

Change to:

```tsx
function NavList({ collapsed }: NavListProps) {
  const { t } = useTranslation();
  const { user } = useAuthState();
  const items = NAV_ITEMS.filter((item) => !item.adminOnly || user?.is_admin);

  return (
    <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2.5 py-2">
      {items.map((item) => {
```

(Only the source array in the `.map()` call changes from `NAV_ITEMS` to `items` — everything inside the map body stays exactly as it is.)

- [ ] **Step 3: Filter in `MobileTabBar.tsx`**

In `frontend/src/components/layout/MobileTabBar.tsx`, the imports currently are:

```tsx
import { useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Dialog } from "@/components/ui/Dialog";
import { GroupedList, GroupedListItem } from "@/components/ui/GroupedList";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
import { useTranslation } from "@/lib/i18n";
import { MOBILE_TAB_PATHS, NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

const TAB_ITEMS = MOBILE_TAB_PATHS.map((path) => NAV_ITEMS.find((item) => item.to === path)!);
const MORE_ITEMS = NAV_ITEMS.filter((item) => !MOBILE_TAB_PATHS.includes(item.to));
```

Change to (module-level `MORE_ITEMS` becomes `ALL_MORE_ITEMS` — the admin-visibility filter needs the current user, which is only known inside the component, so the final per-render list can no longer be a module-level constant):

```tsx
import { useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Dialog } from "@/components/ui/Dialog";
import { GroupedList, GroupedListItem } from "@/components/ui/GroupedList";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
import { useAuthState } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";
import { MOBILE_TAB_PATHS, NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

const TAB_ITEMS = MOBILE_TAB_PATHS.map((path) => NAV_ITEMS.find((item) => item.to === path)!);
const ALL_MORE_ITEMS = NAV_ITEMS.filter((item) => !MOBILE_TAB_PATHS.includes(item.to));
```

Then the component body currently is:

```tsx
export function MobileTabBar() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [moreOpen, setMoreOpen] = useState(false);

  const isMoreActive = MORE_ITEMS.some((item) => isItemActive(location.pathname, item.to));
```

Change to:

```tsx
export function MobileTabBar() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuthState();
  const [moreOpen, setMoreOpen] = useState(false);

  const moreItems = ALL_MORE_ITEMS.filter((item) => !item.adminOnly || user?.is_admin);
  const isMoreActive = moreItems.some((item) => isItemActive(location.pathname, item.to));
```

And further down, the `GroupedList` render currently is:

```tsx
      <Dialog open={moreOpen} onClose={() => setMoreOpen(false)} title={t("nav.more")}>
        <GroupedList>
          {MORE_ITEMS.map((item) => {
```

Change `MORE_ITEMS` to `moreItems`:

```tsx
      <Dialog open={moreOpen} onClose={() => setMoreOpen(false)} title={t("nav.more")}>
        <GroupedList>
          {moreItems.map((item) => {
```

(No other line in this file references `MORE_ITEMS`/`ALL_MORE_ITEMS` — `TAB_ITEMS` is untouched since none of the 4 fixed mobile tab paths are admin-only.)

- [ ] **Step 4: Run the build**

Run: `cd frontend && npm run build`
Expected: succeeds with no new errors.

- [ ] **Step 5: Commit**

```bash
cd frontend
git add src/lib/navigation.ts src/components/layout/Sidebar.tsx src/components/layout/MobileTabBar.tsx
git commit -m "Показывать пункт Админка в навигации только для is_admin"
```

---

## Self-Review Notes

- **Spec coverage:** `last_login_at` → Task 1. Batched stats + `AdminUserRead` → Task 2. Self-lockout guard (backend 400 + frontend hidden buttons) → Task 2 (backend) + Task 3 (frontend, `isSelf` branch in `AdminUserList`). Frontend page/hook/API → Task 3. Nav visibility gating → Task 4. The two explicitly-out-of-scope items from the spec (stronger delete confirmation, self-service become-admin) are correctly absent from every task.
- **Placeholder scan:** every step has literal, complete code — the one place a value can't be hardcoded (the Alembic revision id) is called out explicitly as tool-generated, with exact instructions for what to do with the generated file.
- **Type consistency:** `AdminUserRead`'s 4 new fields (Task 2) match `AdminUser`'s frontend fields (Task 3) name-for-name and in compatible types (`Decimal` → `string` for `net_worth`, matching this codebase's existing convention for other Decimal amounts like `AccountWithBalance.balance: string`). `UserStats`'s fields match how `list_users()` reads them. `NavItem.adminOnly` (Task 4) is read identically in `Sidebar.tsx` and `MobileTabBar.tsx`.
- **No task leaves the build/test suite broken:** Task 1 and Task 2 each end with a full `pytest` run; Task 3 and Task 4 each end with `npm run build`.
