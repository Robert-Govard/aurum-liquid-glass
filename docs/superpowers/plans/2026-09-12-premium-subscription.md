# Free/Premium Subscription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manually-administered Free/Premium tier to Moneta: Free accounts keep the full core (dashboard, transactions, budget, alerts) but are capped on scale (accounts/assets/categories/recurring) and locked out of Crypto/Advice/ROI/CSV-import; an admin grants/revokes Premium per user from the existing admin panel.

**Architecture:** One nullable `premium_until` column on `User`, a single `plan_service.py` as the one place that answers "is this user premium" and "how many of X do they have," a new `get_premium_user` FastAPI dependency (mirrors the existing `get_current_admin`) for whole-feature gates, inline count checks at each creation route for numeric caps, and a new admin-only route to set/clear the expiry. The frontend reads a server-computed `is_premium` boolean, shows a lock badge on gated nav items without hiding them, and renders a shared upsell panel instead of gated content/forms.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic (backend); React/TypeScript, React Query (frontend) — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-12-premium-subscription-design.md`

## Global Constraints

- No payment automation in this iteration — an admin manually sets/clears `premium_until`; there is no payment gateway, webhook, or reminder email.
- All existing users start on Free (`premium_until = NULL`) — nobody inherits Premium automatically.
- `User.is_admin` is always effectively Premium — no separate override flag; admins never call the normal grant mechanism on themselves.
- Data is never deleted or hidden when Premium lapses — only *creating new* items beyond the free limit, and access to the four full-gated features, are blocked. Anything created while Premium stays fully visible/editable forever.
- Export/backup stays free and unlimited on every tier — never gated.
- Crypto/Advice/ROI stay visible in navigation on Free (with a lock badge) — never hidden entirely.
- `insights_service`'s dashboard alert banner (used on Dashboard/Net Worth/Budget) is part of the free core and must NOT be gated — only the dedicated `/advice` page (`advice_service`) is a Premium feature. Do not confuse the two.
- The four numeric limits: accounts (non-archived) ≤ 3, assets ≤ 2, custom categories (`is_default == False`) ≤ 5, active recurring transactions (`is_active == True`) ≤ 5 on Free; unlimited on Premium.
- The four full-gated features: Crypto (`/crypto/*`), Advice (`/advice`), CSV import (`POST /transactions/bulk`), and the frontend-only ROI calculator (`/roi` — no backend route exists for it at all, it's pure client-side arithmetic; its gate is frontend-only, a stated and accepted limitation, not a bug to fix).
- HTTP status for both "feature requires Premium" and "hit a free-tier limit" is **402 Payment Required** — deliberately distinct from the existing 403 (already used for "authenticated but not admin" / "email not verified").
- Every new frontend string goes through `lib/i18n.ts` (`ru` and `en`, kept in sync) — including "Premium" itself, even though it reads the same in both languages.

---

### Task 1: `premium_until` field + `plan_service.py` + `get_premium_user` dependency

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/alembic/versions/b2f6c3d8e451_add_premium_until_to_users.py`
- Create: `backend/app/services/plan_service.py`
- Test: `backend/tests/test_plan_service.py`
- Modify: `backend/app/api/deps.py`

**Interfaces:**
- Produces: `User.premium_until: datetime | None`, `User.is_premium: bool` (property), `plan_service.is_premium(user) -> bool`, `plan_service.FREE_ACCOUNT_LIMIT/FREE_ASSET_LIMIT/FREE_CUSTOM_CATEGORY_LIMIT/FREE_RECURRING_LIMIT` (ints), `plan_service.count_accounts/count_assets/count_custom_categories/count_active_recurring(session, user_id) -> int`, `deps.get_premium_user` (FastAPI dependency) — all consumed by Tasks 2-4.

- [ ] **Step 1: Add the column and computed property to the model**

In `backend/app/models/user.py`, add `timezone` to the existing `from datetime import datetime` import line:

```python
from datetime import datetime, timezone
```

Then add this field after the existing `email_verification_expires_at` field (the last field in the class):

```python
    # Manually set/cleared by an admin via PATCH /admin/users/{id}/premium
    # (see routes/admin.py) — no payment gateway, no automation. NULL means
    # Free (never had Premium, or it was revoked/expired). A future
    # datetime means Premium until that moment. "Forever" is just a date
    # far in the future (the admin UI has a one-click "grant forever"
    # button for this) — no separate boolean, to avoid two fields that
    # could contradict each other about the same fact.
    premium_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_premium(self) -> bool:
        """True if this account currently has an active Premium
        subscription. Admins are always effectively Premium. This lives
        here (not only in services/plan_service.py) so that Pydantic's
        `from_attributes=True` conversion (see schemas/user.py's UserRead)
        picks it up automatically wherever a User ORM object is returned
        directly as a response — services/plan_service.py.is_premium() is
        still the canonical name the rest of the codebase should import
        and call; it just delegates to this property."""
        if self.is_admin:
            return True
        return self.premium_until is not None and self.premium_until > datetime.now(timezone.utc)
```

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/b2f6c3d8e451_add_premium_until_to_users.py`:

```python
"""add premium_until to users

Revision ID: b2f6c3d8e451
Revises: a1e4a2f9c318
Create Date: 2026-09-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f6c3d8e451'
down_revision: Union[str, None] = 'a1e4a2f9c318'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, no backfill needed — NULL is exactly "Free", which is what
    # every existing user should be after this migration (same pattern as
    # last_login_at's own migration).
    op.add_column('users', sa.Column('premium_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'premium_until')
```

- [ ] **Step 3: Write the failing test for `plan_service.is_premium()`**

Create `backend/tests/test_plan_service.py`:

```python
"""plan_service.py — the single place that answers "is this user
premium" and "how many of X do they have." is_premium() is pure logic
(no DB), tested directly on plain User() instances; the count_* helpers
are exercised indirectly by the route tests in test_accounts.py /
test_assets.py / test_categories.py / test_recurring.py, which need a
real database to have anything to count."""
from datetime import datetime, timedelta, timezone

from app.models.user import User
from app.services.plan_service import is_premium


def test_admin_is_always_premium_regardless_of_premium_until():
    admin = User(email="a@example.com", password_hash="x", is_admin=True, premium_until=None)
    assert is_premium(admin) is True


def test_free_user_with_no_premium_until_is_not_premium():
    user = User(email="b@example.com", password_hash="x", is_admin=False, premium_until=None)
    assert is_premium(user) is False


def test_user_with_future_premium_until_is_premium():
    user = User(
        email="c@example.com",
        password_hash="x",
        is_admin=False,
        premium_until=datetime.now(timezone.utc) + timedelta(days=30),
    )
    assert is_premium(user) is True


def test_user_with_past_premium_until_is_not_premium():
    user = User(
        email="d@example.com",
        password_hash="x",
        is_admin=False,
        premium_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert is_premium(user) is False


def test_premium_until_exactly_now_is_treated_as_expired():
    """The boundary is exclusive (`>`, not `>=`) — a premium_until equal
    to the current instant no longer counts as active."""
    now = datetime.now(timezone.utc)
    user = User(email="e@example.com", password_hash="x", is_admin=False, premium_until=now)
    assert is_premium(user) is False
```

- [ ] **Step 4: Run the tests to verify they fail**

Inside the backend's Docker container (see project's `tests/README.md` for how to run pytest — this codebase always runs tests against a real Postgres via Docker, never a local Python env):

Run: `pytest tests/test_plan_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.plan_service'`

- [ ] **Step 5: Implement `plan_service.py`**

Create `backend/app/services/plan_service.py`:

```python
"""The single place that answers "is this user Premium" and "how many
of X do they already have." Every Premium-gated route imports from here
instead of re-deriving the same checks — see the spec's Global
Constraints for the exact limits and which features are fully gated."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.asset import Asset
from app.models.category import Category
from app.models.recurring import RecurringTransaction
from app.models.user import User
from app.services.scoped import scoped

FREE_ACCOUNT_LIMIT = 3
FREE_ASSET_LIMIT = 2
FREE_CUSTOM_CATEGORY_LIMIT = 5
FREE_RECURRING_LIMIT = 5


def is_premium(user: User) -> bool:
    """Canonical entry point the rest of the codebase should import —
    delegates to User.is_premium (see models/user.py for why the actual
    logic lives on the model instead of here)."""
    return user.is_premium


async def count_accounts(session: AsyncSession, user_id: int) -> int:
    stmt = scoped(select(func.count()).select_from(Account), Account, user_id).where(
        Account.is_archived.is_(False)
    )
    return (await session.execute(stmt)).scalar_one()


async def count_assets(session: AsyncSession, user_id: int) -> int:
    stmt = scoped(select(func.count()).select_from(Asset), Asset, user_id)
    return (await session.execute(stmt)).scalar_one()


async def count_custom_categories(session: AsyncSession, user_id: int) -> int:
    stmt = scoped(select(func.count()).select_from(Category), Category, user_id).where(
        Category.is_default.is_(False)
    )
    return (await session.execute(stmt)).scalar_one()


async def count_active_recurring(session: AsyncSession, user_id: int) -> int:
    stmt = scoped(select(func.count()).select_from(RecurringTransaction), RecurringTransaction, user_id).where(
        RecurringTransaction.is_active.is_(True)
    )
    return (await session.execute(stmt)).scalar_one()
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/test_plan_service.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Add the `get_premium_user` dependency**

In `backend/app/api/deps.py`, add this import:

```python
from app.services.plan_service import is_premium
```

Then add this function at the end of the file, after `get_current_admin`:

```python
async def get_premium_user(current_user: User = Depends(get_current_user)) -> User:
    if not is_premium(current_user):
        raise HTTPException(status_code=402, detail="Premium subscription required")
    return current_user
```

- [ ] **Step 8: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS (this task adds a nullable column and new, unused-so-far code — nothing existing should break).

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/user.py backend/alembic/versions/b2f6c3d8e451_add_premium_until_to_users.py backend/app/services/plan_service.py backend/tests/test_plan_service.py backend/app/api/deps.py
git commit -m "Добавить поле premium_until и сервис проверки тарифа"
```

---

### Task 2: Numeric limits on account/asset/category/recurring creation

**Files:**
- Modify: `backend/app/api/routes/accounts.py`
- Modify: `backend/app/api/routes/assets.py`
- Modify: `backend/app/api/routes/categories.py`
- Modify: `backend/app/api/routes/recurring.py`
- Test: `backend/tests/test_accounts.py`
- Test: `backend/tests/test_assets.py`
- Test: `backend/tests/test_categories.py`
- Test: `backend/tests/test_recurring.py`

**Interfaces:**
- Consumes: `plan_service.is_premium`, `plan_service.FREE_ACCOUNT_LIMIT/FREE_ASSET_LIMIT/FREE_CUSTOM_CATEGORY_LIMIT/FREE_RECURRING_LIMIT`, `plan_service.count_accounts/count_assets/count_custom_categories/count_active_recurring` (Task 1).

This task adds one `if not is_premium(...): ...` block to each of the four creation routes. The check lives in the route (not the underlying service function) so that none of `account_service.py`/`assets.py`'s/`categories.py`'s/`recurring_service.py`'s existing business logic changes — this is an access-control concern, the same layer `get_current_admin` already lives at, not a domain-modeling one.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_accounts.py`:

```python
from app.services.plan_service import FREE_ACCOUNT_LIMIT
from sqlalchemy import update

from app.models.user import User


async def test_free_user_cannot_exceed_the_account_limit(client):
    # Every test starts against a freshly truncated database (see
    # conftest.py's autouse _clean_database fixture) — this user has zero
    # accounts at the start of this test regardless of what other tests do.
    for i in range(FREE_ACCOUNT_LIMIT):
        resp = await client.post("/accounts", json={"name": f"Account {i}", "type": "checking", "currency": "USD"})
        assert resp.status_code == 201

    over_limit = await client.post("/accounts", json={"name": "One too many", "type": "checking", "currency": "USD"})
    assert over_limit.status_code == 402


async def test_premium_user_has_no_account_limit(client, test_sessionmaker):
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "test@example.com").values(is_admin=True))
        await session.commit()

    for i in range(FREE_ACCOUNT_LIMIT + 2):
        resp = await client.post("/accounts", json={"name": f"Account {i}", "type": "checking", "currency": "USD"})
        assert resp.status_code == 201
```

Add to `backend/tests/test_assets.py`:

```python
from app.services.plan_service import FREE_ASSET_LIMIT


async def test_free_user_cannot_exceed_the_asset_limit(client):
    for i in range(FREE_ASSET_LIMIT):
        resp = await client.post("/assets", json=_payload(name=f"Asset {i}"))
        assert resp.status_code == 201

    over_limit = await client.post("/assets", json=_payload(name="One too many"))
    assert over_limit.status_code == 402
```

Add to `backend/tests/test_categories.py`:

```python
from app.services.plan_service import FREE_CUSTOM_CATEGORY_LIMIT


async def test_free_user_cannot_exceed_the_custom_category_limit(client):
    for i in range(FREE_CUSTOM_CATEGORY_LIMIT):
        resp = await client.post("/categories", json={"name": f"Custom {i}", "kind": "expense", "color": "#e34948"})
        assert resp.status_code == 201

    over_limit = await client.post(
        "/categories", json={"name": "One too many", "kind": "expense", "color": "#e34948"}
    )
    assert over_limit.status_code == 402
```

Add to `backend/tests/test_recurring.py`:

```python
from app.services.plan_service import FREE_RECURRING_LIMIT


async def test_free_user_cannot_exceed_the_recurring_limit(client, account_id):
    for i in range(FREE_RECURRING_LIMIT):
        resp = await client.post("/recurring", json=_payload(account_id, description=f"Bill {i}"))
        assert resp.status_code == 201

    over_limit = await client.post("/recurring", json=_payload(account_id, description="One too many"))
    assert over_limit.status_code == 402
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_accounts.py tests/test_assets.py tests/test_categories.py tests/test_recurring.py -v -k limit`
Expected: FAIL — every new test gets `201` where it expects `402` (no limit is enforced yet).

- [ ] **Step 3: Add the limit check to `accounts.py`**

In `backend/app/api/routes/accounts.py`, add this import:

```python
from fastapi import APIRouter, Depends, HTTPException
```

(adds `HTTPException` to the existing `from fastapi import APIRouter, Depends` line), and:

```python
from app.services.plan_service import FREE_ACCOUNT_LIMIT, count_accounts, is_premium
```

Then change `create_account_route` from:

```python
@router.post("", response_model=AccountWithBalance, status_code=201)
async def create_account_route(
    payload: AccountCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AccountWithBalance:
    return await create_account(session, payload, current_user.id)
```

to:

```python
@router.post("", response_model=AccountWithBalance, status_code=201)
async def create_account_route(
    payload: AccountCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AccountWithBalance:
    if not is_premium(current_user) and await count_accounts(session, current_user.id) >= FREE_ACCOUNT_LIMIT:
        raise HTTPException(status_code=402, detail="Free plan account limit reached")
    return await create_account(session, payload, current_user.id)
```

- [ ] **Step 4: Add the limit check to `assets.py`**

In `backend/app/api/routes/assets.py`, add this import:

```python
from app.services.plan_service import FREE_ASSET_LIMIT, count_assets, is_premium
```

Then change the start of `create_asset` from:

```python
@router.post("", response_model=AssetRead, status_code=201)
async def create_asset(
    payload: AssetCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AssetRead:
    asset = Asset(
```

to:

```python
@router.post("", response_model=AssetRead, status_code=201)
async def create_asset(
    payload: AssetCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AssetRead:
    if not is_premium(current_user) and await count_assets(session, current_user.id) >= FREE_ASSET_LIMIT:
        raise HTTPException(status_code=402, detail="Free plan asset limit reached")
    asset = Asset(
```

(`HTTPException` is already imported in this file — confirmed by its existing `from fastapi import APIRouter, Depends, HTTPException` line.)

- [ ] **Step 5: Add the limit check to `categories.py`**

In `backend/app/api/routes/categories.py`, add this import:

```python
from app.services.plan_service import FREE_CUSTOM_CATEGORY_LIMIT, count_custom_categories, is_premium
```

Then change the start of `create_category` from:

```python
@router.post("", response_model=CategoryRead, status_code=201)
async def create_category(
    payload: CategoryCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Category:
    if payload.parent_id is not None:
```

to:

```python
@router.post("", response_model=CategoryRead, status_code=201)
async def create_category(
    payload: CategoryCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Category:
    if not is_premium(current_user) and await count_custom_categories(session, current_user.id) >= FREE_CUSTOM_CATEGORY_LIMIT:
        raise HTTPException(status_code=402, detail="Free plan custom category limit reached")
    if payload.parent_id is not None:
```

(`HTTPException` is already imported in this file.)

- [ ] **Step 6: Add the limit check to `recurring.py`**

In `backend/app/api/routes/recurring.py`, add this import:

```python
from fastapi import APIRouter, Depends, HTTPException
```

(adds `HTTPException`), and:

```python
from app.services.plan_service import FREE_RECURRING_LIMIT, count_active_recurring, is_premium
```

Then change `create_recurring_route` from:

```python
@router.post("", response_model=RecurringTransactionRead, status_code=201)
async def create_recurring_route(
    payload: RecurringTransactionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringTransactionRead:
    return await create_recurring(session, payload, current_user.id)
```

to:

```python
@router.post("", response_model=RecurringTransactionRead, status_code=201)
async def create_recurring_route(
    payload: RecurringTransactionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringTransactionRead:
    if not is_premium(current_user) and await count_active_recurring(session, current_user.id) >= FREE_RECURRING_LIMIT:
        raise HTTPException(status_code=402, detail="Free plan recurring transaction limit reached")
    return await create_recurring(session, payload, current_user.id)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/test_accounts.py tests/test_assets.py tests/test_categories.py tests/test_recurring.py -v`
Expected: PASS (all tests in these four files, including the pre-existing ones — confirm nothing regressed).

- [ ] **Step 8: Run the full suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/api/routes/accounts.py backend/app/api/routes/assets.py backend/app/api/routes/categories.py backend/app/api/routes/recurring.py backend/tests/test_accounts.py backend/tests/test_assets.py backend/tests/test_categories.py backend/tests/test_recurring.py
git commit -m "Добавить лимиты бесплатного тарифа на счета/активы/категории/регулярные платежи"
```

---

### Task 3: Full-feature gates — Crypto, Advice, CSV import

**Files:**
- Modify: `backend/app/api/routes/crypto.py`
- Modify: `backend/app/api/routes/advice.py`
- Modify: `backend/app/api/routes/transactions.py`
- Test: `backend/tests/test_crypto.py`
- Test: `backend/tests/test_advice.py`
- Test: `backend/tests/test_transactions.py`

**Interfaces:**
- Consumes: `deps.get_premium_user` (Task 1).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_crypto.py`:

```python
async def test_free_user_cannot_access_crypto(client):
    resp = await client.get("/crypto/portfolios")
    assert resp.status_code == 402


async def test_premium_user_can_access_crypto(client, test_sessionmaker):
    from sqlalchemy import update

    from app.models.user import User

    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "test@example.com").values(is_admin=True))
        await session.commit()

    resp = await client.get("/crypto/portfolios")
    assert resp.status_code == 200
```

Add to `backend/tests/test_advice.py`:

```python
async def test_free_user_cannot_access_advice(client):
    resp = await client.get("/advice")
    assert resp.status_code == 402


async def test_premium_user_can_access_advice(client, test_sessionmaker):
    from sqlalchemy import update

    from app.models.user import User

    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "test@example.com").values(is_admin=True))
        await session.commit()

    resp = await client.get("/advice")
    assert resp.status_code == 200
```

Add to `backend/tests/test_transactions.py`:

```python
async def test_free_user_cannot_use_bulk_import(client, account_id):
    resp = await client.post(
        "/transactions/bulk",
        json={
            "items": [
                {
                    "account_id": account_id,
                    "type": "expense",
                    "amount": "10.00",
                    "description": "CSV row",
                    "date": "2026-01-15",
                }
            ]
        },
    )
    assert resp.status_code == 402


async def test_premium_user_can_use_bulk_import(client, account_id, test_sessionmaker):
    from sqlalchemy import update

    from app.models.user import User

    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "test@example.com").values(is_admin=True))
        await session.commit()

    resp = await client.post(
        "/transactions/bulk",
        json={
            "items": [
                {
                    "account_id": account_id,
                    "type": "expense",
                    "amount": "10.00",
                    "description": "CSV row",
                    "date": "2026-01-15",
                }
            ]
        },
    )
    assert resp.status_code == 201
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_crypto.py tests/test_advice.py tests/test_transactions.py -v -k "free_user_cannot or premium_user_can"`
Expected: FAIL — the "free_user_cannot" tests get `200`/`201` instead of `402` (nothing is gated yet); the "premium_user_can" tests should already pass (admin already has full access today) — that's expected and fine, they exist to guard against a future regression.

- [ ] **Step 3: Gate the Crypto router**

In `backend/app/api/routes/crypto.py`, add this import:

```python
from app.api.deps import get_current_user, get_premium_user, get_session
```

(adds `get_premium_user` to the existing import line), then change:

```python
router = APIRouter(prefix="/crypto", tags=["crypto"])
```

to:

```python
router = APIRouter(prefix="/crypto", tags=["crypto"], dependencies=[Depends(get_premium_user)])
```

Every route in this file keeps its own `current_user: User = Depends(get_current_user)` parameter unchanged — FastAPI caches dependency resolution per request, so `get_current_user` still only actually runs once even though it's now reached both via the router-level `get_premium_user` chain and each route's own parameter.

- [ ] **Step 4: Gate the Advice router**

In `backend/app/api/routes/advice.py`, add this import:

```python
from app.api.deps import get_current_user, get_premium_user, get_session
```

then change:

```python
router = APIRouter(prefix="/advice", tags=["advice"])
```

to:

```python
router = APIRouter(prefix="/advice", tags=["advice"], dependencies=[Depends(get_premium_user)])
```

- [ ] **Step 5: Gate only the CSV bulk-import route**

In `backend/app/api/routes/transactions.py`, add this import:

```python
from app.api.deps import get_current_user, get_premium_user, get_session
```

Then change `bulk_create_transactions` from:

```python
@router.post("/bulk", response_model=TransactionBulkCreateResult, status_code=201)
async def bulk_create_transactions(
    payload: TransactionBulkCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TransactionBulkCreateResult:
```

to:

```python
@router.post("/bulk", response_model=TransactionBulkCreateResult, status_code=201)
async def bulk_create_transactions(
    payload: TransactionBulkCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_premium_user),
) -> TransactionBulkCreateResult:
```

(only this one route's `current_user` dependency changes — every other route in `transactions.py` keeps `Depends(get_current_user)`, unaffected.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_crypto.py tests/test_advice.py tests/test_transactions.py -v`
Expected: PASS (all tests in these three files).

- [ ] **Step 7: Run the full suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/routes/crypto.py backend/app/api/routes/advice.py backend/app/api/routes/transactions.py backend/tests/test_crypto.py backend/tests/test_advice.py backend/tests/test_transactions.py
git commit -m "Закрыть Crypto, Советы и импорт CSV платной подпиской"
```

---

### Task 4: Admin management of Premium

**Files:**
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/services/user_service.py`
- Modify: `backend/app/api/routes/admin.py`
- Test: `backend/tests/test_admin.py`

**Interfaces:**
- Produces: `UserRead.is_premium: bool`, `AdminUserRead.premium_until: datetime | None`, `UserPremiumUpdate` (request schema, field `premium_until: datetime | None`), `UserPremiumRead` (response schema, `UserRead` + `premium_until: datetime | None`), `user_service.update_user_premium(session, user_id, payload) -> User`, route `PATCH /admin/users/{user_id}/premium`.

`UserRead.is_premium` needs no explicit population code anywhere — `UserRead.model_config`'s `from_attributes=True` conversion already picks up `User.is_premium` (Task 1's model property) automatically wherever a raw `User` ORM object is returned through `response_model=UserRead` (both `/auth/me` and `PATCH /admin/users/{id}` already do this today and need zero changes for the new field to appear).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_admin.py`:

```python
async def test_admin_can_grant_premium_to_a_user(client, test_sessionmaker):
    admin_tokens = await _register(client, "premiumadmin@example.com")
    await _make_admin(test_sessionmaker, "premiumadmin@example.com")

    target_tokens = await _register(client, "premiumtarget@example.com")

    resp = await client.patch(
        f"/admin/users/{_user_id_from_token(target_tokens)}/premium",
        json={"premium_until": "2099-01-01T00:00:00Z"},
        headers=_auth(admin_tokens["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["is_premium"] is True
    assert resp.json()["premium_until"].startswith("2099-01-01")

    # Confirm it's actually enforced, not just reported: the target user's
    # own token can now hit a Premium-gated route.
    crypto_resp = await client.get("/crypto/portfolios", headers=_auth(target_tokens["access_token"]))
    assert crypto_resp.status_code == 200


async def test_admin_can_revoke_premium(client, test_sessionmaker):
    admin_tokens = await _register(client, "premiumadmin2@example.com")
    await _make_admin(test_sessionmaker, "premiumadmin2@example.com")

    target_tokens = await _register(client, "premiumtarget2@example.com")
    target_id = _user_id_from_token(target_tokens)

    await client.patch(
        f"/admin/users/{target_id}/premium",
        json={"premium_until": "2099-01-01T00:00:00Z"},
        headers=_auth(admin_tokens["access_token"]),
    )

    resp = await client.patch(
        f"/admin/users/{target_id}/premium",
        json={"premium_until": None},
        headers=_auth(admin_tokens["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["is_premium"] is False
    assert resp.json()["premium_until"] is None


async def test_non_admin_cannot_grant_premium(client):
    resp = await client.patch("/admin/users/1/premium", json={"premium_until": "2099-01-01T00:00:00Z"})
    assert resp.status_code == 403


async def test_grant_premium_to_unknown_user_is_404(client, test_sessionmaker):
    admin_tokens = await _register(client, "premiumadmin3@example.com")
    await _make_admin(test_sessionmaker, "premiumadmin3@example.com")

    resp = await client.patch(
        "/admin/users/999999/premium",
        json={"premium_until": "2099-01-01T00:00:00Z"},
        headers=_auth(admin_tokens["access_token"]),
    )
    assert resp.status_code == 404
```

Add this small helper near the top of `backend/tests/test_admin.py`, alongside the existing `_register`/`_make_admin`/`_auth` helpers:

```python
import jwt as pyjwt


def _user_id_from_token(tokens: dict) -> int:
    """Decodes the access token's `sub` claim without verifying the
    signature — this test file already has the real signing secret via
    the autouse _jwt_secret fixture in test_auth.py, but pulling the user
    id out of the token this way avoids threading it through _register's
    return value just for these four tests."""
    payload = pyjwt.decode(tokens["access_token"], options={"verify_signature": False})
    return int(payload["sub"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_admin.py -v -k premium`
Expected: FAIL with 404/405 (the route doesn't exist yet).

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas/user.py`, add `is_premium: bool` to `UserRead`:

```python
class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool
    is_active: bool
    is_premium: bool
    created_at: datetime
```

Add `premium_until: datetime | None` to `AdminUserRead`:

```python
class AdminUserRead(UserRead):
    """GET /api/admin/users only — /api/auth/me keeps using plain UserRead,
    deliberately never exposing these per-user stats about "yourself" via
    that shape (the normal dashboard is where a user sees their own
    numbers)."""

    last_login_at: datetime | None
    accounts_count: int
    transactions_count: int
    net_worth: Decimal
    currency: str
    premium_until: datetime | None
```

Add two new schemas at the end of the file:

```python
class UserPremiumUpdate(BaseModel):
    premium_until: datetime | None


class UserPremiumRead(UserRead):
    """PATCH /api/admin/users/{id}/premium's response — UserRead's
    is_premium plus the raw premium_until date, so the admin UI can show
    exactly what was just set without a second request."""

    premium_until: datetime | None
```

- [ ] **Step 4: Update `list_users()` and add `update_user_premium()`**

In `backend/app/services/user_service.py`, add `premium_until=user.premium_until` to each `AdminUserRead(...)` construction in `list_users()` (note `is_premium` needs NO explicit line here — `AdminUserRead(id=user.id, ...)` is built with keyword arguments, so any field not explicitly passed would actually raise a pydantic validation error; add `is_premium=user.is_premium` too):

```python
    return [
        AdminUserRead(
            id=user.id,
            email=user.email,
            is_admin=user.is_admin,
            is_active=user.is_active,
            is_premium=user.is_premium,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            accounts_count=stats.get(user.id, empty_stats).accounts_count,
            transactions_count=stats.get(user.id, empty_stats).transactions_count,
            net_worth=stats.get(user.id, empty_stats).net_worth,
            currency=currencies.get(user.id, "USD"),
            premium_until=user.premium_until,
        )
        for user in users
    ]
```

Change the import line to bring in the new schema:

```python
from app.schemas.user import AdminUserRead, UserPremiumUpdate, UserUpdate
```

Add this function at the end of the file:

```python
async def update_user_premium(session: AsyncSession, user_id: int, payload: UserPremiumUpdate) -> User:
    """No self-lockout guard here (unlike update_user()/delete_user()):
    an admin setting their own premium_until has zero effect either way
    — User.is_premium already returns True for any admin regardless of
    this field — so there is nothing destructive to guard against."""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.premium_until = payload.premium_until
    await session.commit()
    await session.refresh(user)
    return user
```

- [ ] **Step 5: Add the route**

In `backend/app/api/routes/admin.py`, change the schema import line:

```python
from app.schemas.user import AdminUserRead, UserPremiumRead, UserPremiumUpdate, UserRead, UserUpdate
```

Change the service import line:

```python
from app.services.user_service import delete_user, list_users, update_user, update_user_premium
```

Add this route after `update_user_route`:

```python
@router.patch("/users/{user_id}/premium", response_model=UserPremiumRead)
async def update_user_premium_route(
    user_id: int,
    payload: UserPremiumUpdate,
    session: AsyncSession = Depends(get_session),
) -> User:
    return await update_user_premium(session, user_id, payload)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_admin.py -v`
Expected: PASS (all tests in this file, including pre-existing ones).

- [ ] **Step 7: Run the full suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/user.py backend/app/services/user_service.py backend/app/api/routes/admin.py backend/tests/test_admin.py
git commit -m "Добавить управление тарифом Premium в админ-панель"
```

---

### Task 5: Frontend plumbing — session type, i18n, nav lock badges, shared upsell component

**Files:**
- Modify: `frontend/src/lib/auth.ts`
- Modify: `frontend/src/lib/i18n.ts`
- Modify: `frontend/src/lib/navigation.ts`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/components/layout/MobileTabBar.tsx`
- Create: `frontend/src/components/premium/PremiumRequired.tsx`

**Interfaces:**
- Produces: `CurrentUser.is_premium: boolean`, `NavItem.premiumOnly?: boolean`, `<PremiumRequired />` component — consumed by Task 6.

- [ ] **Step 1: Add `is_premium` to `CurrentUser`**

In `frontend/src/lib/auth.ts`, change:

```ts
export interface CurrentUser {
  id: number;
  email: string;
  is_admin: boolean;
  is_active: boolean;
}
```

to:

```ts
export interface CurrentUser {
  id: number;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  is_premium: boolean;
}
```

(`fetchCurrentUser()` already does a plain `response.json()` cast with no field allowlist, so the new field flows through automatically — no other change needed in this file.)

- [ ] **Step 2: Add the i18n strings**

In `frontend/src/lib/i18n.ts`, add to the `ru` block (anywhere near the other `nav.*`/`admin.*` keys is fine — exact position doesn't matter, TypeScript's key-set check is what matters):

```ts
  "nav.premiumBadge": "Premium",
  "premium.requiredTitle": "Доступно в Premium",
  "premium.requiredBody": "Эта функция доступна только с платной подпиской. Подробности уточните у администратора вашего сервера.",
  "premium.limitReached": "Достигнут лимит бесплатного тарифа. Подробности уточните у администратора вашего сервера.",
  "admin.premiumBadge": "Premium",
  "admin.managePremium": "Управление подпиской",
  "admin.premiumModalTitle": "Управление Premium",
  "admin.premiumActiveUntil": "Premium активен до {{date}}",
  "admin.premiumInactive": "Сейчас на бесплатном тарифе",
  "admin.premiumUntilLabel": "Дата окончания",
  "admin.premiumGrantUntil": "Выдать до даты",
  "admin.premiumGrantForever": "Выдать навсегда",
  "admin.premiumRevoke": "Снять Premium",
```

And to the `en` block:

```ts
  "nav.premiumBadge": "Premium",
  "premium.requiredTitle": "Available in Premium",
  "premium.requiredBody": "This feature requires a paid subscription. Ask your server's administrator for details.",
  "premium.limitReached": "You've reached the free plan limit. Ask your server's administrator for details.",
  "admin.premiumBadge": "Premium",
  "admin.managePremium": "Manage subscription",
  "admin.premiumModalTitle": "Manage Premium",
  "admin.premiumActiveUntil": "Premium active until {{date}}",
  "admin.premiumInactive": "Currently on the Free plan",
  "admin.premiumUntilLabel": "Expires on",
  "admin.premiumGrantUntil": "Grant until date",
  "admin.premiumGrantForever": "Grant forever",
  "admin.premiumRevoke": "Revoke Premium",
```

- [ ] **Step 3: Add `premiumOnly` to `NavItem` and mark Crypto/ROI/Advice**

In `frontend/src/lib/navigation.ts`, change the `NavItem` interface:

```ts
export interface NavItem {
  labelKey: TranslationKey;
  to: string;
  icon: LucideIcon;
  disabled?: boolean;
  // Only rendered in Sidebar.tsx/MobileTabBar.tsx when the current user's
  // is_admin is true — both filter NAV_ITEMS on this before rendering.
  adminOnly?: boolean;
  // Shown with a lock badge (not hidden) in Sidebar.tsx/MobileTabBar.tsx
  // when the current user's is_premium is false — the item stays
  // clickable either way; the destination page itself renders
  // <PremiumRequired /> instead of its normal content (see
  // components/premium/PremiumRequired.tsx).
  premiumOnly?: boolean;
}
```

Change the three relevant entries in `NAV_ITEMS`:

```ts
  { labelKey: "nav.crypto", to: "/crypto", icon: Coins, premiumOnly: true },
  { labelKey: "nav.roi", to: "/roi", icon: Calculator, premiumOnly: true },
```

and:

```ts
  { labelKey: "nav.advice", to: "/advice", icon: Lightbulb, premiumOnly: true },
```

(leave every other entry in `NAV_ITEMS` unchanged.)

- [ ] **Step 4: Show the lock badge in `Sidebar.tsx`**

In `frontend/src/components/layout/Sidebar.tsx`, add the `Lock` icon to the existing lucide import:

```ts
import { Lock, PanelLeftClose, PanelLeftOpen } from "lucide-react";
```

Change the active (non-disabled) `NavLink` branch inside `NavList` from:

```tsx
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-2 hover:text-text-primary",
                collapsed && "justify-center px-0",
                isActive && "bg-surface-2 text-text-primary"
              )
            }
          >
            <Icon size={18} className="shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
          </NavLink>
        );
```

to:

```tsx
        const locked = item.premiumOnly && !user?.is_premium;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-2 hover:text-text-primary",
                collapsed && "justify-center px-0",
                isActive && "bg-surface-2 text-text-primary"
              )
            }
          >
            <Icon size={18} className="shrink-0" />
            {!collapsed && (
              <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                <span className="truncate">{label}</span>
                {locked && <Lock size={12} className="shrink-0 text-text-muted" />}
              </span>
            )}
          </NavLink>
        );
```

- [ ] **Step 5: Show the lock badge in `MobileTabBar.tsx`**

In `frontend/src/components/layout/MobileTabBar.tsx`, add the `Lock` icon to the existing lucide import:

```ts
import { Lock, MoreHorizontal } from "lucide-react";
```

Change the non-disabled `GroupedListItem` branch inside the `moreItems.map(...)` from:

```tsx
            return (
              <GroupedListItem
                key={item.to}
                icon={Icon}
                label={t(item.labelKey)}
                onClick={() => {
                  navigate(item.to);
                  setMoreOpen(false);
                }}
              />
            );
```

to:

```tsx
            const locked = item.premiumOnly && !user?.is_premium;
            return (
              <GroupedListItem
                key={item.to}
                icon={Icon}
                label={t(item.labelKey)}
                trailing={locked ? <Lock size={14} className="text-text-muted" /> : undefined}
                onClick={() => {
                  navigate(item.to);
                  setMoreOpen(false);
                }}
              />
            );
```

- [ ] **Step 6: Create the shared upsell component**

Create `frontend/src/components/premium/PremiumRequired.tsx`:

```tsx
import { Lock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { useTranslation } from "@/lib/i18n";

/** Rendered instead of a page's normal content when the current user
 * isn't on Premium — used by CryptoPage/AdvicePage/RoiPage/CsvImportPage
 * (see the spec: these four features stay visible in navigation with a
 * lock badge rather than being hidden, so this is what a free user sees
 * on actually opening one of them). There's no payment flow here —
 * subscriptions are granted manually by the server's admin. */
export function PremiumRequired() {
  const { t } = useTranslation();

  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
        <Lock size={28} className="text-text-muted" />
        <p className="text-sm font-semibold text-text-primary">{t("premium.requiredTitle")}</p>
        <p className="max-w-sm text-sm text-text-muted">{t("premium.requiredBody")}</p>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 7: Verify the build**

Run: `cd frontend && npm run build`
Expected: PASS (`tsc -b` then `vite build`, no type errors — this task doesn't wire `PremiumRequired` into any page yet, that's Task 6, so no visual change is expected).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/auth.ts frontend/src/lib/i18n.ts frontend/src/lib/navigation.ts frontend/src/components/layout/Sidebar.tsx frontend/src/components/layout/MobileTabBar.tsx frontend/src/components/premium/PremiumRequired.tsx
git commit -m "Добавить признак Premium в сессию, значки-замочки в меню и общий экран-заглушку"
```

---

### Task 6: Gate the four Premium pages + limit-aware form errors

**Files:**
- Modify: `frontend/src/pages/CryptoPage.tsx`
- Modify: `frontend/src/pages/AdvicePage.tsx`
- Modify: `frontend/src/pages/RoiPage.tsx`
- Modify: `frontend/src/pages/CsvImportPage.tsx`
- Modify: `frontend/src/components/accounts/AccountFormModal.tsx`
- Modify: `frontend/src/components/networth/AssetFormModal.tsx`
- Modify: `frontend/src/components/categories/CategoryFormModal.tsx`
- Modify: `frontend/src/components/recurring/RecurringFormModal.tsx`

**Interfaces:**
- Consumes: `<PremiumRequired />`, `CurrentUser.is_premium` (Task 5), `ApiError` (existing, `frontend/src/api/client.ts`).

- [ ] **Step 1: Gate `CryptoPage.tsx`**

In `frontend/src/pages/CryptoPage.tsx`, add these imports:

```tsx
import { PremiumRequired } from "@/components/premium/PremiumRequired";
import { useAuthState } from "@/lib/auth";
```

Add this as the very first line inside the `CryptoPage` component function body (before any other hook call), and the early return right after it:

```tsx
export function CryptoPage() {
  const { user } = useAuthState();
  if (!user?.is_premium) return <PremiumRequired />;

  // ... rest of the existing component body, unchanged
```

(Find the actual `export function CryptoPage() {` line in the file and insert these two lines as the first thing inside it, before its existing `useState`/`useMemo` calls.)

- [ ] **Step 2: Gate `AdvicePage.tsx`**

In `frontend/src/pages/AdvicePage.tsx`, add these imports:

```tsx
import { PremiumRequired } from "@/components/premium/PremiumRequired";
import { useAuthState } from "@/lib/auth";
```

Add the same two-line guard as the first thing inside the page's exported component function, before its existing `useAdvice()` call.

- [ ] **Step 3: Gate `RoiPage.tsx`**

In `frontend/src/pages/RoiPage.tsx`, add these imports:

```tsx
import { PremiumRequired } from "@/components/premium/PremiumRequired";
import { useAuthState } from "@/lib/auth";
```

Add the same two-line guard as the first thing inside `export function RoiPage() {`, before its existing `useState` calls. This is the ONE purely-frontend gate in the whole feature (see Global Constraints — ROI has no backend route to protect).

- [ ] **Step 4: Gate `CsvImportPage.tsx`**

In `frontend/src/pages/CsvImportPage.tsx`, add these imports:

```tsx
import { PremiumRequired } from "@/components/premium/PremiumRequired";
import { useAuthState } from "@/lib/auth";
```

Add the same two-line guard as the first thing inside `export function CsvImportPage() {`, before its existing hooks. (The backend already 402s `POST /transactions/bulk` for a non-Premium user as of Task 3 — this frontend gate means a free user never even sees the upload form in the first place, rather than getting partway through and hitting a raw error.)

- [ ] **Step 5: Show a Premium-specific message when a create-form hits the 402 limit**

In `frontend/src/components/accounts/AccountFormModal.tsx`, add this import after the `"react"` import:

```tsx
import { ApiError } from "@/api/client";
```

Change:

```tsx
    } catch {
      setError(t("account.form.saveError"));
    }
```

to:

```tsx
    } catch (err) {
      setError(err instanceof ApiError && err.status === 402 ? t("premium.limitReached") : t("account.form.saveError"));
    }
```

In `frontend/src/components/networth/AssetFormModal.tsx`, add the same `import { ApiError } from "@/api/client";` after its `"react"` import, and change:

```tsx
    } catch {
      setError(t("netWorth.form.saveError"));
    }
```

to:

```tsx
    } catch (err) {
      setError(err instanceof ApiError && err.status === 402 ? t("premium.limitReached") : t("netWorth.form.saveError"));
    }
```

In `frontend/src/components/categories/CategoryFormModal.tsx`, add the same import after its `"react"` import, and change:

```tsx
    } catch {
      setError(t("category.form.saveError"));
    }
```

to:

```tsx
    } catch (err) {
      setError(err instanceof ApiError && err.status === 402 ? t("premium.limitReached") : t("category.form.saveError"));
    }
```

In `frontend/src/components/recurring/RecurringFormModal.tsx`, add the same import after its `"react"` import, and change:

```tsx
    } catch {
      setError(t("recurring.form.saveError"));
    }
```

to:

```tsx
    } catch (err) {
      setError(err instanceof ApiError && err.status === 402 ? t("premium.limitReached") : t("recurring.form.saveError"));
    }
```

- [ ] **Step 6: Verify the build**

Run: `cd frontend && npm run build`
Expected: PASS, zero type errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/CryptoPage.tsx frontend/src/pages/AdvicePage.tsx frontend/src/pages/RoiPage.tsx frontend/src/pages/CsvImportPage.tsx frontend/src/components/accounts/AccountFormModal.tsx frontend/src/components/networth/AssetFormModal.tsx frontend/src/components/categories/CategoryFormModal.tsx frontend/src/components/recurring/RecurringFormModal.tsx
git commit -m "Показывать заглушку Premium на закрытых страницах и лимитах вместо технической ошибки"
```

---

### Task 7: Admin UI for granting/revoking Premium

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/admin.ts`
- Modify: `frontend/src/hooks/useAdmin.ts`
- Modify: `frontend/src/components/admin/AdminUserList.tsx`
- Create: `frontend/src/components/admin/AdminPremiumModal.tsx`
- Modify: `frontend/src/pages/AdminPage.tsx`

**Interfaces:**
- Consumes: `PATCH /admin/users/{id}/premium` (Task 4).

- [ ] **Step 1: Add the fields to the `AdminUser` type**

In `frontend/src/types/index.ts`, change the `AdminUser` interface:

```ts
export interface AdminUser {
  id: number;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  is_premium: boolean;
  created_at: string;
  last_login_at: string | null;
  accounts_count: number;
  transactions_count: number;
  net_worth: string;
  currency: string;
  premium_until: string | null;
}
```

- [ ] **Step 2: Add the API call**

In `frontend/src/api/admin.ts`, add this function:

```ts
export function updateAdminUserPremium(id: number, premiumUntil: string | null) {
  return api.patch<AdminUser>(`/admin/users/${id}/premium`, { premium_until: premiumUntil });
}
```

- [ ] **Step 3: Add the mutation hook**

In `frontend/src/hooks/useAdmin.ts`, change the import line:

```ts
import { deleteAdminUser, fetchAdminUserDashboard, fetchAdminUsers, updateAdminUser, updateAdminUserPremium } from "@/api/admin";
```

Add this hook after `useUpdateAdminUser`:

```ts
export function useUpdateAdminUserPremium() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, premiumUntil }: { id: number; premiumUntil: string | null }) =>
      updateAdminUserPremium(id, premiumUntil),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}
```

- [ ] **Step 4: Add the badge and manage-button to `AdminUserList.tsx`**

In `frontend/src/components/admin/AdminUserList.tsx`, add the `BadgeCheck` icon to the existing lucide import:

```tsx
import { BadgeCheck, Trash2 } from "lucide-react";
```

Add `onManagePremium` to the props interface:

```tsx
interface AdminUserListProps {
  items: AdminUser[];
  currentUserId: number | undefined;
  onView: (user: AdminUser) => void;
  onToggleActive: (user: AdminUser) => void;
  onDelete: (user: AdminUser) => void;
  onManagePremium: (user: AdminUser) => void;
}
```

Add `onManagePremium` to the destructured function parameters:

```tsx
export function AdminUserList({ items, currentUserId, onView, onToggleActive, onDelete, onManagePremium }: AdminUserListProps) {
```

Add the Premium badge next to the existing admin/disabled badges — change:

```tsx
                {user.is_admin && (
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none text-text-muted">
                    {t("admin.adminBadge")}
                  </span>
                )}
                {!user.is_active && (
```

to:

```tsx
                {user.is_admin && (
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none text-text-muted">
                    {t("admin.adminBadge")}
                  </span>
                )}
                {user.is_premium && (
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none text-text-muted">
                    {t("admin.premiumBadge")}
                  </span>
                )}
                {!user.is_active && (
```

Add a manage-premium button next to the existing delete button — change:

```tsx
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
```

to:

```tsx
            {!isSelf && (
              <span className="flex shrink-0 items-center gap-3">
                <Switch
                  checked={user.is_active}
                  onChange={() => onToggleActive(user)}
                  aria-label={user.is_active ? t("admin.disable") : t("admin.enable")}
                />
                <button
                  type="button"
                  onClick={() => onManagePremium(user)}
                  aria-label={t("admin.managePremium")}
                  className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                >
                  <BadgeCheck size={16} />
                </button>
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
```

- [ ] **Step 5: Create the management modal**

Create `frontend/src/components/admin/AdminPremiumModal.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label } from "@/components/ui/Input";
import { useUpdateAdminUserPremium } from "@/hooks/useAdmin";
import { formatFullDate } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { AdminUser } from "@/types";

const FOREVER_YEARS = 100;

interface AdminPremiumModalProps {
  user: AdminUser | null;
  onClose: () => void;
}

/** Opened from AdminUserList's per-row "manage subscription" button.
 * Permanently mounted (like AdminUserDashboardModal) with a displayUser
 * that lags one render behind `user` becoming null, so Dialog's own
 * close-fade animation has a real user object to render text about
 * while it plays — see Dialog.tsx's contract. */
export function AdminPremiumModal({ user, onClose }: AdminPremiumModalProps) {
  const { t } = useTranslation();
  const updatePremium = useUpdateAdminUserPremium();
  const [displayUser, setDisplayUser] = useState<AdminUser | null>(null);
  const [date, setDate] = useState("");

  useEffect(() => {
    if (user) {
      setDisplayUser(user);
      setDate("");
    }
  }, [user]);

  function grantUntil(iso: string) {
    if (!displayUser) return;
    updatePremium.mutate({ id: displayUser.id, premiumUntil: iso }, { onSuccess: onClose });
  }

  function grantForever() {
    const forever = new Date();
    forever.setFullYear(forever.getFullYear() + FOREVER_YEARS);
    grantUntil(forever.toISOString());
  }

  function revoke() {
    if (!displayUser) return;
    updatePremium.mutate({ id: displayUser.id, premiumUntil: null }, { onSuccess: onClose });
  }

  return (
    <Dialog open={user !== null} onClose={onClose} title={t("admin.premiumModalTitle")}>
      {displayUser && (
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            {displayUser.is_premium && displayUser.premium_until
              ? t("admin.premiumActiveUntil", { date: formatFullDate(displayUser.premium_until) })
              : t("admin.premiumInactive")}
          </p>
          <div>
            <Label htmlFor="premium-until-date">{t("admin.premiumUntilLabel")}</Label>
            <Input id="premium-until-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              disabled={!date || updatePremium.isPending}
              onClick={() => grantUntil(new Date(date).toISOString())}
            >
              {t("admin.premiumGrantUntil")}
            </Button>
            <Button type="button" variant="secondary" disabled={updatePremium.isPending} onClick={grantForever}>
              {t("admin.premiumGrantForever")}
            </Button>
            {displayUser.is_premium && (
              <Button type="button" variant="secondary" disabled={updatePremium.isPending} onClick={revoke}>
                {t("admin.premiumRevoke")}
              </Button>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}
```

- [ ] **Step 6: Wire it into `AdminPage.tsx`**

In `frontend/src/pages/AdminPage.tsx`, add the import:

```tsx
import { AdminPremiumModal } from "@/components/admin/AdminPremiumModal";
```

Add a second piece of state next to `selectedUser`:

```tsx
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [premiumUser, setPremiumUser] = useState<AdminUser | null>(null);
```

Pass the new prop to `AdminUserList`:

```tsx
            <AdminUserList
              items={users ?? []}
              currentUserId={currentUser?.id}
              onView={setSelectedUser}
              onToggleActive={handleToggleActive}
              onDelete={handleDelete}
              onManagePremium={setPremiumUser}
            />
```

Render the modal next to the existing one:

```tsx
      <AdminUserDashboardModal user={selectedUser} onClose={() => setSelectedUser(null)} />
      <AdminPremiumModal user={premiumUser} onClose={() => setPremiumUser(null)} />
```

- [ ] **Step 7: Verify the build**

Run: `cd frontend && npm run build`
Expected: PASS, zero type errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/admin.ts frontend/src/hooks/useAdmin.ts frontend/src/components/admin/AdminUserList.tsx frontend/src/components/admin/AdminPremiumModal.tsx frontend/src/pages/AdminPage.tsx
git commit -m "Добавить управление подпиской Premium в интерфейс админ-панели"
```

## Manual verification (not automatable by the implementer)

After this plan merges, in a browser:
1. As a Free-tier user, confirm Crypto/ROI/Советы show a lock badge in the nav but are still clickable, and open to the "Available in Premium" panel rather than a raw error.
2. Create accounts/assets/custom categories/recurring transactions up to each free limit and confirm the form shows the Premium message (not a generic save error) on the one over the limit.
3. As the admin, open a user's row, grant Premium via a specific date and via "grant forever," confirm the badge and lock icons update after each, then revoke and confirm the user drops back to Free (including that their over-the-old-limit data from while they were Premium is still visible, not deleted).
4. Confirm exporting/importing a backup is unaffected on Free.
