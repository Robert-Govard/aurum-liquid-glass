# Multi-Tenant Data Isolation — Part 1 (Core CRUD) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every user's accounts, categories, tags, budgets, goals,
recurring-transaction templates, and app settings fully private to them —
the first of three plans that together retire Aurum's single-shared-dataset
model in favor of per-user data, now that the Multi-Tenant Auth Foundation
plan has landed (`users`, JWT login, `get_current_user`).

**Architecture:** A `user_id` column (nullable for now — see Global
Constraints) on each of the 7 tables this plan touches, a shared
`app/services/scoped.py` helper every service routes its queries through
instead of hand-writing `.where(user_id == ...)`, `current_user:
User = Depends(get_current_user)` threaded through each of the 7 routers,
and registration (`auth_service.register`) extended to seed each new
user's own default categories + settings row instead of the old
instance-wide boot-time seed. Transactions, assets, and crypto (Part 2) and
the read-only aggregation routers — dashboard/net_worth/cash_flow/reports/
advice/insights/backup (Part 3) — follow in separate plans, because they
either touch many of these tables at once (Part 3) or are large enough
domains to deserve their own plan (Part 2).

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2,
Postgres — same stack as the Auth Foundation plan; no new dependencies.

**Spec:** [docs/superpowers/specs/2026-09-08-multi-tenant-backend-design.md](../specs/2026-09-08-multi-tenant-backend-design.md)

## Global Constraints

- `user_id` is added **nullable** in this plan's migration, not `NOT NULL`
  yet. Reason: unlike the Auth Foundation plan (which only added brand-new
  tables), this plan adds a column to tables existing code already writes
  to. A `NOT NULL` column with no default would break every INSERT from
  code this plan hasn't touched yet the instant the migration runs. Once
  Part 2 and Part 3 finish converting every remaining table/router, a
  final migration (in Part 3) flips every `user_id` column to `NOT NULL` in
  one pass, once every writer in the codebase sets it.
- Every listing/lookup query against a user-owned table MUST go through
  `app/services/scoped.py`'s `scoped()` or `get_owned_or_404()` — no
  service in this plan writes its own `.where(Model.user_id == ...)`.
- A row that exists but belongs to another user returns **404, not 403** —
  `get_owned_or_404` never confirms to a caller that an id they don't own
  exists at all.
- No email verification, password reset, or invite codes anywhere (still
  true, inherited from the Auth Foundation plan's constraints).
- **Known, accepted consequence of merging this plan:** the current web
  frontend (`frontend/`) is not updated by this plan or its two follow-ups.
  Once these routers require a Bearer JWT, the existing `LoginGate`/
  `lib/auth.ts` (built for instance-wide Basic Auth) can no longer reach
  any of the 7 converted endpoints — the web UI will show errors for
  Accounts, Categories, Tags, Budgets, Goals, Recurring, and Settings until
  a separate frontend plan (not yet written) adds real login/registration
  screens. This is intentional sequencing, not an oversight: the backend
  and frontend auth models can't be migrated as one atomic change without
  either plan becoming unreviewably large.

---

## Task 1: Migration — `user_id` on the 7 core tables

**Files:**
- Create: `backend/alembic/versions/a3f7c2e9b148_add_user_id_to_core_tables.py`
- Modify: `backend/app/models/account.py`
- Modify: `backend/app/models/category.py`
- Modify: `backend/app/models/tag.py`
- Modify: `backend/app/models/budget.py`
- Modify: `backend/app/models/goal.py`
- Modify: `backend/app/models/recurring.py`
- Modify: `backend/app/models/settings.py`

**Interfaces:**
- Produces: every one of `Account`, `Category`, `Tag`, `Budget`, `Goal`,
  `RecurringTransaction`, `AppSettings` gains `user_id: Mapped[int | None]`
  (FK → `users.id`, `ondelete="CASCADE"`), nullable for now per Global
  Constraints. `AppSettings.user_id` is additionally `unique=True` (one
  settings row per user). `Tag.name`'s uniqueness becomes per-user instead
  of global.

- [ ] **Step 1: Confirm the real constraint name for `tags.name` before writing the downgrade**

Run: `docker compose exec db psql -U aurum -d aurum -c "\d tags"`
Expected output includes a line like `"tags_name_key" UNIQUE CONSTRAINT, btree (name)`. If the actual name differs, use that name instead of `tags_name_key` everywhere below.

- [ ] **Step 2: Add `user_id` to each model**

Modify `backend/app/models/account.py` — add after the `is_archived` column:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

Add `ForeignKey` to the existing `from sqlalchemy import Boolean, Enum, String` import line (`from sqlalchemy import Boolean, Enum, ForeignKey, String`).

Modify `backend/app/models/category.py` — add after `parent_id`:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

(`ForeignKey` is already imported in this file.)

Modify `backend/app/models/tag.py` — replace the whole `Tag` class:

```python
class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tags_user_id_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    transactions: Mapped[list["Transaction"]] = relationship(secondary=transaction_tags, back_populates="tags")
```

Add `UniqueConstraint` to this file's `from sqlalchemy import Column, ForeignKey, String, Table` line (`from sqlalchemy import Column, ForeignKey, String, Table, UniqueConstraint`).

Modify `backend/app/models/budget.py` — add after `monthly_limit`:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

(`ForeignKey` already imported.)

Modify `backend/app/models/goal.py` — add after `target_date` in `Goal`:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

(`ForeignKey` already imported.)

Modify `backend/app/models/recurring.py` — add after `is_active`:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

(`ForeignKey` already imported.)

Modify `backend/app/models/settings.py` — add `ForeignKey` to the `sqlalchemy` import, and add after `id`:

```python
from sqlalchemy import ForeignKey, Integer, Numeric, String
```

```python
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, unique=True
    )
```

- [ ] **Step 3: Write the migration**

The current head is `5c9e2a7f1b34` (from the Auth Foundation plan). Create
`backend/alembic/versions/a3f7c2e9b148_add_user_id_to_core_tables.py`:

```python
"""add user_id to accounts, categories, tags, budgets, goals, recurring_transactions, app_settings

Revision ID: a3f7c2e9b148
Revises: 5c9e2a7f1b34
Create Date: 2026-09-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f7c2e9b148'
down_revision: Union[str, None] = '5c9e2a7f1b34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_accounts_user_id', 'accounts', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_accounts_user_id', 'accounts', ['user_id'])

    op.add_column('categories', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_categories_user_id', 'categories', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_categories_user_id', 'categories', ['user_id'])

    # Tags move from a single global namespace to one namespace per user.
    op.drop_constraint('tags_name_key', 'tags', type_='unique')
    op.add_column('tags', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_tags_user_id', 'tags', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_unique_constraint('uq_tags_user_id_name', 'tags', ['user_id', 'name'])

    op.add_column('budgets', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_budgets_user_id', 'budgets', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_budgets_user_id', 'budgets', ['user_id'])

    op.add_column('goals', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_goals_user_id', 'goals', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_goals_user_id', 'goals', ['user_id'])

    op.add_column('recurring_transactions', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_recurring_transactions_user_id', 'recurring_transactions', 'users', ['user_id'], ['id'], ondelete='CASCADE'
    )
    op.create_index('ix_recurring_transactions_user_id', 'recurring_transactions', ['user_id'])

    op.add_column('app_settings', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_app_settings_user_id', 'app_settings', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_unique_constraint('uq_app_settings_user_id', 'app_settings', ['user_id'])


def downgrade() -> None:
    op.drop_constraint('uq_app_settings_user_id', 'app_settings', type_='unique')
    op.drop_constraint('fk_app_settings_user_id', 'app_settings', type_='foreignkey')
    op.drop_column('app_settings', 'user_id')

    op.drop_index('ix_recurring_transactions_user_id', table_name='recurring_transactions')
    op.drop_constraint('fk_recurring_transactions_user_id', 'recurring_transactions', type_='foreignkey')
    op.drop_column('recurring_transactions', 'user_id')

    op.drop_index('ix_goals_user_id', table_name='goals')
    op.drop_constraint('fk_goals_user_id', 'goals', type_='foreignkey')
    op.drop_column('goals', 'user_id')

    op.drop_index('ix_budgets_user_id', table_name='budgets')
    op.drop_constraint('fk_budgets_user_id', 'budgets', type_='foreignkey')
    op.drop_column('budgets', 'user_id')

    op.drop_constraint('uq_tags_user_id_name', 'tags', type_='unique')
    op.drop_constraint('fk_tags_user_id', 'tags', type_='foreignkey')
    op.drop_column('tags', 'user_id')
    op.create_unique_constraint('tags_name_key', 'tags', ['name'])

    op.drop_index('ix_categories_user_id', table_name='categories')
    op.drop_constraint('fk_categories_user_id', 'categories', type_='foreignkey')
    op.drop_column('categories', 'user_id')

    op.drop_index('ix_accounts_user_id', table_name='accounts')
    op.drop_constraint('fk_accounts_user_id', 'accounts', type_='foreignkey')
    op.drop_column('accounts', 'user_id')
```

If Step 1 found a different real constraint name than `tags_name_key`, use that name in both `upgrade()`'s `drop_constraint` call and `downgrade()`'s final `create_unique_constraint` call.

- [ ] **Step 4: Verify the migration runs both ways**

Run: `docker compose exec backend alembic upgrade head` (against the real dev DB), then `docker compose exec backend alembic downgrade -1`, then `docker compose exec backend alembic upgrade head` again.
Expected: all three commands succeed with no errors, ending back at `head`.

- [ ] **Step 5: Run the full test suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS — the `_test_database` fixture runs `alembic upgrade head` fresh, so this is the real test of the migration; nothing in application code reads the new columns yet, so behavior is unchanged (154 passing, same as before this plan).

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/a3f7c2e9b148_add_user_id_to_core_tables.py \
  backend/app/models/account.py backend/app/models/category.py backend/app/models/tag.py \
  backend/app/models/budget.py backend/app/models/goal.py backend/app/models/recurring.py \
  backend/app/models/settings.py
git commit -m "Добавить nullable user_id в accounts/categories/tags/budgets/goals/recurring/app_settings"
```

---

## Task 2: Shared scoped-query helper

**Files:**
- Create: `backend/app/services/scoped.py`
- Test: `backend/tests/test_scoped.py`

**Interfaces:**
- Produces: `scoped(stmt: Select, model: type[ModelT], user_id: int) -> Select`
  and `async get_owned_or_404(session: AsyncSession, model: type[ModelT],
  obj_id: int, user_id: int, detail: str = "Not found") -> ModelT` (raises
  `fastapi.HTTPException(404, detail)` if missing/not owned). Every
  remaining task in this plan imports both from here.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_scoped.py`:

```python
"""Unit tests for the shared scoped-query helper every user-owned-table
service routes through (see services/scoped.py)."""
from fastapi import HTTPException
from sqlalchemy import select
import pytest

from app.models.account import Account
from app.models.enums import AccountType
from app.models.user import User
from app.services.scoped import get_owned_or_404, scoped


async def _make_user(session, email: str) -> User:
    """`Account.user_id` is a real foreign key to `users.id` — these tests
    insert Account rows directly (bypassing the HTTP API), so they need a
    real User row to point at, not just an arbitrary integer."""
    user = User(email=email, password_hash="x")
    session.add(user)
    await session.flush()
    return user


async def test_scoped_only_returns_the_given_users_rows(test_sessionmaker):
    async with test_sessionmaker() as session:
        user_a = await _make_user(session, "scoped-a@example.com")
        user_b = await _make_user(session, "scoped-b@example.com")
        session.add_all(
            [
                Account(name="A's account", type=AccountType.CHECKING, currency="USD", user_id=user_a.id),
                Account(name="B's account", type=AccountType.CHECKING, currency="USD", user_id=user_b.id),
            ]
        )
        await session.commit()

        stmt = scoped(select(Account), Account, user_id=user_a.id)
        rows = (await session.execute(stmt)).scalars().all()
        assert [a.name for a in rows] == ["A's account"]


async def test_get_owned_or_404_returns_the_row_when_owned(test_sessionmaker):
    async with test_sessionmaker() as session:
        user = await _make_user(session, "owned@example.com")
        account = Account(name="Mine", type=AccountType.CHECKING, currency="USD", user_id=user.id)
        session.add(account)
        await session.commit()

        found = await get_owned_or_404(session, Account, account.id, user_id=user.id)
        assert found.id == account.id


async def test_get_owned_or_404_404s_for_someone_elses_row(test_sessionmaker):
    async with test_sessionmaker() as session:
        owner = await _make_user(session, "owner@example.com")
        other = await _make_user(session, "other@example.com")
        account = Account(name="Theirs", type=AccountType.CHECKING, currency="USD", user_id=owner.id)
        session.add(account)
        await session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await get_owned_or_404(session, Account, account.id, user_id=other.id)
        assert exc_info.value.status_code == 404


async def test_get_owned_or_404_404s_for_a_nonexistent_id(test_sessionmaker):
    async with test_sessionmaker() as session:
        user = await _make_user(session, "nonexistent-id@example.com")
        with pytest.raises(HTTPException) as exc_info:
            await get_owned_or_404(session, Account, 999999, user_id=user.id)
        assert exc_info.value.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_scoped.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.scoped'`

- [ ] **Step 3: Implement `app/services/scoped.py`**

Create `backend/app/services/scoped.py`:

```python
"""Shared query-scoping helpers for per-user data isolation.

Every domain table a user can own (accounts, categories, tags, budgets,
goals, recurring transactions, app_settings, and more added by later
plans) carries a `user_id` column. Every service function that lists or
fetches rows from one of these tables routes through one of the two
helpers below instead of writing `.where(Model.user_id == ...)` by hand —
see the multi-tenant backend design spec's "Authorization / data
isolation" section for why: one place to get isolation right instead of
one per call site.
"""
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


def scoped(stmt: Select, model: type[ModelT], user_id: int) -> Select:
    """Adds a `WHERE model.user_id == user_id` clause to an existing
    select statement. Use for any list/filter query against a user-owned
    table."""
    return stmt.where(model.user_id == user_id)


async def get_owned_or_404(
    session: AsyncSession, model: type[ModelT], obj_id: int, user_id: int, detail: str = "Not found"
) -> ModelT:
    """Fetches one row by primary key AND owner in a single query — 404s
    if the row doesn't exist OR belongs to someone else. Deliberately the
    same response either way: confirming "that id exists, it's just not
    yours" would leak information a caller has no business learning.
    Replaces `session.get(Model, id)` wherever the table is user-owned."""
    result = await session.execute(select(model).where(model.id == obj_id, model.user_id == user_id))
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=detail)
    return obj
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_scoped.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scoped.py backend/tests/test_scoped.py
git commit -m "Добавить общий scoped-query хелпер для изоляции данных по пользователю"
```

---

## Task 3: Per-user seeding — refactor `db/seed.py`, extend registration, add `GET /api/auth/me`

**Files:**
- Modify: `backend/app/db/seed.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/app/api/routes/auth.py`
- Test: `backend/tests/test_auth.py` (extend)

**Interfaces:**
- Consumes: `User` (Auth Foundation plan), `UserRead` (`app/schemas/user.py`,
  Auth Foundation plan), `get_current_user` (`app/api/deps.py`, Auth
  Foundation plan).
- Produces: `seed_default_categories(session, user_id)` and
  `seed_default_app_settings(session, user_id)` (both now per-user, no
  longer instance-wide singletons); `register()` in `auth_service.py` now
  also seeds these for the new user; `GET /api/auth/me` returning
  `UserRead` for the caller.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_auth.py`. `select` is already imported at
the top of this file (from Task 2's test) — only these two new model
imports are needed:

```python
from app.models.category import Category
from app.models.settings import AppSettings


async def test_register_seeds_the_new_users_own_categories_and_settings(client, test_sessionmaker):
    resp = await client.post("/auth/register", json={"email": "seeded@example.com", "password": "hunter22"})
    tokens = resp.json()

    me_resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me_resp.status_code == 200
    user_id = me_resp.json()["id"]

    async with test_sessionmaker() as session:
        categories = (await session.execute(select(Category).where(Category.user_id == user_id))).scalars().all()
        assert len(categories) == 17  # 8 expense + 9 income, see DEFAULT_*_CATEGORIES in db/seed.py

        settings_row = (
            await session.execute(select(AppSettings).where(AppSettings.user_id == user_id))
        ).scalar_one()
        assert settings_row.currency  # created, not left missing


async def test_get_me_requires_auth(client):
    # The client fixture's default Authorization header is valid — override
    # it with an empty one for this one call to simulate no token at all.
    resp = await client.get("/auth/me", headers={"Authorization": ""})
    assert resp.status_code == 401


async def test_get_me_returns_the_callers_own_email(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert "email" in body
    assert "password" not in body and "password_hash" not in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_auth.py -v -k "seeds_the_new_users or get_me"`
Expected: FAIL — `test_register_seeds...` fails because categories/settings aren't created with a `user_id` yet (in fact `Category`/`AppSettings` have no rows created by `register()` at all right now); `test_get_me...` fails with 404 (no `/auth/me` route yet).

- [ ] **Step 3: Refactor `db/seed.py` to be per-user**

Modify `backend/app/db/seed.py` — replace the whole file:

```python
"""Seeds a new user's default category set and settings row at
registration time (see services/auth_service.py:register). Each user gets
their own copy — these are no longer instance-wide singletons.

The expense categories are assigned hues from the dataviz skill's validated
8-slot categorical palette, in the palette's fixed slot order (never
reordered/cycled) so the dashboard donut chart is colorblind-safe out of the
box. See CLAUDE.md-adjacent design notes in UPDATES.md for the source.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.category import Category
from app.models.enums import CategoryKind
from app.models.settings import AppSettings

# (name, icon, color) — order doubles as sort_order / palette slot index.
DEFAULT_EXPENSE_CATEGORIES = [
    ("Housing & Utilities", "home", "#2a78d6"),  # slot 1 blue
    ("Groceries", "shopping-basket", "#1baf7a"),  # slot 3 aqua
    ("Dining Out", "utensils", "#eb6834"),  # slot 2 orange
    ("Transportation", "car", "#4a3aa7"),  # slot 7 violet
    ("Health & Fitness", "heart-pulse", "#e34948"),  # slot 8 red
    ("Shopping", "shopping-bag", "#eda100"),  # slot 4 yellow
    ("Entertainment", "clapperboard", "#e87ba4"),  # slot 5 magenta
    ("Subscriptions", "repeat", "#008300"),  # slot 6 green
]

DEFAULT_INCOME_CATEGORIES = [
    ("Salary", "banknote", "#2a78d6"),
    ("Freelance", "briefcase", "#1baf7a"),
    ("Investments", "trending-up", "#4a3aa7"),
    ("Gifts", "gift", "#e87ba4"),
    ("Business Income", "building-2", "#eb6834"),
    ("Rental Income", "key", "#eda100"),
    ("Benefits", "hand-coins", "#008300"),
    ("Item Sales", "tag", "#e34948"),
    ("Other Income", "plus-circle", "#898781"),
]


async def seed_default_categories(session: AsyncSession, user_id: int) -> None:
    """Creates this user's default category set. Called once, at
    registration (services/auth_service.py:register) — never checks for
    existing rows first, since a brand-new user has none."""
    order = 0
    for name, icon, color in DEFAULT_EXPENSE_CATEGORIES:
        session.add(
            Category(
                user_id=user_id,
                name=name,
                kind=CategoryKind.EXPENSE,
                icon=icon,
                color=color,
                sort_order=order,
                is_default=True,
            )
        )
        order += 1
    for name, icon, color in DEFAULT_INCOME_CATEGORIES:
        session.add(
            Category(
                user_id=user_id,
                name=name,
                kind=CategoryKind.INCOME,
                icon=icon,
                color=color,
                sort_order=order,
                is_default=True,
            )
        )
        order += 1


async def seed_default_app_settings(session: AsyncSession, user_id: int) -> None:
    """Creates this user's settings row, seeded with AURUM_DEFAULT_CURRENCY.
    Called once, at registration — never checks for an existing row first,
    since a brand-new user has none."""
    session.add(AppSettings(user_id=user_id, currency=get_settings().default_currency))
```

Note what's gone: `seed_default_account` is removed entirely — there is no
per-user auto-created account (the spec's registration flow only seeds
categories + settings; a user adds their first account themselves via the
existing Accounts page/`POST /accounts`). Both remaining functions no
longer check for an existing row first (the old instance-wide versions
were idempotent because they ran on every app boot; these run exactly
once, at registration, for a user who by definition has no rows yet) and
no longer call `session.commit()` themselves — the caller
(`auth_service.register`) commits once for the whole registration,
consistent with how it already handles the `User` row.

- [ ] **Step 4: Remove instance-wide seeding from `main.py`'s lifespan**

Modify `backend/app/main.py` — replace:

```python
from app.db.seed import seed_default_account, seed_default_app_settings, seed_default_categories
from app.db.session import AsyncSessionLocal

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as session:
        await seed_default_categories(session)
        await seed_default_account(session)
        await seed_default_app_settings(session)
    yield
```

with:

```python
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_jwt_secret_is_configured()
    yield
```

(The `_check_jwt_secret_is_configured()` call and its function definition
already exist in this file from the Auth Foundation plan's final-review
fix — do not duplicate it, just make sure the boot-time category/account/
settings seeding calls that used to run before it are gone. `AsyncSessionLocal`
is no longer imported here since nothing in this function needs a session
anymore — remove that import too if nothing else in the file uses it.)

- [ ] **Step 5: Extend `auth_service.register()` and add `/auth/me`**

Modify `backend/app/services/auth_service.py` — `from app.models.user
import User` is already there (used by `register`/`login`); add one new
import line alongside the existing `from app.core.security import (...)`
block:

```python
from app.db.seed import seed_default_app_settings, seed_default_categories
```

Modify `register()`'s body — insert the seeding calls right after
`await session.flush()` (which assigns `user.id`) and before the existing
`return await _issue_token_pair(session, user.id)` line:

```python
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    await session.flush()  # assigns user.id without ending the transaction

    await seed_default_categories(session, user.id)
    await seed_default_app_settings(session, user.id)

    return await _issue_token_pair(session, user.id)
```

(`_issue_token_pair` already calls `session.commit()`, so this stays one
atomic transaction — a crash between seeding and commit leaves nothing
half-created.)

Modify `backend/app/api/routes/auth.py` — add a `GET /auth/me` route.
Add these imports:

```python
from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.user import UserRead
```

(Merge with the existing `from app.api.deps import get_session` line
rather than duplicating it.) Add the route itself, after the existing
`logout_route`:

```python
@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_auth.py -v`
Expected: PASS — all tests in the file, including the two new ones.

- [ ] **Step 7: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: **the whole run fails at collection**, not just a handful of
test failures — `tests/conftest.py` still imports `seed_default_account,
seed_default_app_settings, seed_default_categories` from `app.db.seed`
with their old signatures/names, and `seed_default_account` no longer
exists at all after Step 3's rewrite. Pytest reports this as an
`ImportError`/`ERROR` during collection (visible near the top of the
output, something like `ERRORS` / `ImportError: cannot import name
'seed_default_account'`), and no individual test in the suite actually
runs. **This is the expected, correct state to leave the codebase in at
the end of this task** — Task 4 (test infrastructure rewrite) is what
fixes `conftest.py` to match. Do not attempt to fix `conftest.py` here,
and do not treat this collection error as something you need to resolve
before committing. Paste the collection error into your report so the
next task's context is clear, then proceed to Step 8.

- [ ] **Step 8: Commit**

```bash
git add backend/app/db/seed.py backend/app/main.py backend/app/services/auth_service.py \
  backend/app/api/routes/auth.py backend/tests/test_auth.py
git commit -m "Сделать сидирование категорий/настроек per-user при регистрации, добавить GET /api/auth/me"
```

---

## Task 4: Test infrastructure rewrite

**Files:**
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/helpers.py`
- Delete: `backend/tests/test_app_settings_seed.py`
- Modify: `backend/tests/test_cors.py`

**Interfaces:**
- Produces: `client` fixture (existing name, new behavior — auto-registers
  and authenticates one test user per test), `register_user(client, email,
  password="hunter22") -> dict` and `auth_headers(token: str) -> dict` in
  `tests/helpers.py` for isolation tests that need a *second* user.
  `account_id` and `categories` fixtures keep their existing names/shapes
  but source their data differently (see below).

- [ ] **Step 1: Rewrite the `client`, `_clean_database`, and `account_id` fixtures**

Modify `backend/tests/conftest.py`. Remove the `seed_default_categories,
seed_default_account, seed_default_app_settings` import (the whole `from
app.db.seed import ...` line) — nothing in this file calls the old
instance-wide seed functions anymore. Replace the `_clean_database` fixture:

```python
@pytest_asyncio.fixture(autouse=True)
async def _clean_database(test_sessionmaker):
    """Wipe every table before each test — no instance-wide seeding
    happens anymore; each test's `client` fixture registers its own user,
    whose categories/settings are seeded by that registration call, same
    as a real signup."""
    async with test_sessionmaker() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
        await session.commit()
    yield
```

Replace the `client` fixture:

```python
@pytest_asyncio.fixture
async def client(test_sessionmaker) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api") as ac:
        register_resp = await ac.post("/auth/register", json={"email": "test@example.com", "password": "hunter22"})
        token = register_resp.json()["access_token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac
    app.dependency_overrides.clear()
```

Replace the `account_id` fixture (there is no more auto-seeded account —
each test that needs one creates it):

```python
@pytest_asyncio.fixture
async def account_id(client: AsyncClient) -> int:
    """Creates one account for the test's default user (see the `client`
    fixture) — every transaction needs one, and there's no more
    auto-seeded account (registration only seeds categories/settings)."""
    resp = await client.post("/accounts", json={"name": "Main Account", "type": "checking", "currency": "USD"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]
```

The `categories` fixture is unchanged — it already just does `client.get("/categories")`, which now transparently returns the `client` fixture's one auto-registered user's own seeded categories instead of instance-wide ones; same shape, same 17 default rows, just per-user now.

- [ ] **Step 2: Add shared isolation-test helpers**

Modify `backend/tests/helpers.py` — add:

```python
async def register_user(client, email: str, password: str = "hunter22") -> dict:
    """Registers a second user for an isolation test (the `client` fixture
    already auto-registers and authenticates as one default user — use
    this to bring in another one and compare what each can/can't see).
    Returns the /auth/register response body (access_token, refresh_token,
    token_type)."""
    resp = await client.post("/auth/register", json={"email": email, "password": password})
    return resp.json()


def auth_headers(token: str) -> dict:
    """Pass as `headers=auth_headers(token)` on one httpx call to act as a
    different user than the client fixture's default, for that call only."""
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 3: Delete the obsolete singleton-settings test**

Delete `backend/tests/test_app_settings_seed.py` — it tested
`seed_default_app_settings(session)` as an instance-wide singleton
get-or-create at id=1, a concept that no longer exists (`AppSettings` is
now created once per user, at registration, by `auth_service.register`,
already covered by Task 3's `test_register_seeds_the_new_users_own_categories_and_settings`).

```bash
rm backend/tests/test_app_settings_seed.py
```

- [ ] **Step 4: Fix `test_cors.py` if it depends on unauthenticated access**

Read `backend/tests/test_cors.py` first. If any test in it calls a
protected endpoint without the `client` fixture's default auth (e.g. it
builds its own bare `AsyncClient`/`ASGITransport` to test CORS headers on
an unauthenticated request), it may now get a 401 instead of whatever it
expected — CORS headers are still present on a 401 response (CORS
middleware runs regardless of the route's own status code), so if the
test's assertions are purely about headers (not body/status), it likely
still passes unchanged. If it asserts a 200 status specifically, update it
to expect 401 instead, or route it through an authenticated call — use
your judgment based on what the test is actually verifying (CORS
mechanics, not auth), and note in your report which case it was.

- [ ] **Step 5: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS across the board now — every existing test file that uses
the `client`/`account_id`/`categories` fixtures keeps working because
those fixtures now transparently register/authenticate/seed per test,
same effective behavior as the old instance-wide boot seeding, just scoped
to one user per test instead of the whole instance.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/conftest.py backend/tests/helpers.py backend/tests/test_cors.py
git rm backend/tests/test_app_settings_seed.py
git commit -m "Переписать тестовую инфраструктуру на per-user регистрацию вместо инстанс-wide сидирования"
```

---

## Task 5: Wire `accounts`

**Files:**
- Modify: `backend/app/services/account_service.py`
- Modify: `backend/app/api/routes/accounts.py`
- Create: `backend/tests/test_accounts.py`

**Interfaces:**
- Consumes: `get_current_user` (`app/api/deps.py`), `scoped`,
  `get_owned_or_404` (`app/services/scoped.py`).
- Produces: `list_accounts(session, include_archived, user_id)`,
  `create_account(session, payload, user_id)`,
  `update_account(session, account_id, payload, user_id)`,
  `delete_account(session, account_id, user_id)` — signatures every
  future task/plan touching accounts must match.

- [ ] **Step 1: Write the failing isolation test**

Create `backend/tests/test_accounts.py`:

```python
"""Accounts: CRUD plus per-user isolation (no test file existed for this
router before — it was only ever exercised indirectly via other tests'
`account_id` fixture)."""
from tests.helpers import auth_headers, register_user


async def test_create_and_list_account(client):
    resp = await client.post("/accounts", json={"name": "Checking", "type": "checking", "currency": "USD"})
    assert resp.status_code == 201
    listed = await client.get("/accounts")
    assert [a["name"] for a in listed.json()] == ["Checking"]


async def test_user_a_cannot_see_user_bs_accounts(client):
    a_account = (await client.post("/accounts", json={"name": "A's", "type": "checking", "currency": "USD"})).json()

    b_tokens = await register_user(client, "b@example.com")
    b_account = (
        await client.post(
            "/accounts", json={"name": "B's", "type": "checking", "currency": "USD"}, headers=auth_headers(b_tokens["access_token"])
        )
    ).json()

    a_list = (await client.get("/accounts")).json()
    assert [a["id"] for a in a_list] == [a_account["id"]]

    b_list = (await client.get("/accounts", headers=auth_headers(b_tokens["access_token"]))).json()
    assert [a["id"] for a in b_list] == [b_account["id"]]


async def test_user_a_cannot_update_user_bs_account(client):
    b_tokens = await register_user(client, "b2@example.com")
    b_account = (
        await client.post(
            "/accounts", json={"name": "B's", "type": "checking", "currency": "USD"}, headers=auth_headers(b_tokens["access_token"])
        )
    ).json()

    resp = await client.patch(f"/accounts/{b_account['id']}", json={"name": "Hijacked"})
    assert resp.status_code == 404


async def test_user_a_cannot_delete_user_bs_account(client):
    b_tokens = await register_user(client, "b3@example.com")
    b_account = (
        await client.post(
            "/accounts", json={"name": "B's", "type": "checking", "currency": "USD"}, headers=auth_headers(b_tokens["access_token"])
        )
    ).json()

    resp = await client.delete(f"/accounts/{b_account['id']}")
    assert resp.status_code == 404

    still_there = await client.get("/accounts", headers=auth_headers(b_tokens["access_token"]))
    assert len(still_there.json()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_accounts.py -v`
Expected: FAIL — accounts aren't scoped yet, so `test_user_a_cannot_see_user_bs_accounts` sees both accounts in each list.

- [ ] **Step 3: Wire the service**

Modify `backend/app/services/account_service.py` — add the import:

```python
from app.services.scoped import get_owned_or_404, scoped
```

Replace `list_accounts`:

```python
async def list_accounts(session: AsyncSession, include_archived: bool, user_id: int) -> list[AccountWithBalance]:
    stmt = scoped(select(Account), Account, user_id).order_by(Account.name)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    accounts = (await session.execute(stmt)).scalars().all()
    balances = await _account_balances(session)
    return [_to_read(account, balances.get(account.id, Decimal("0"))) for account in accounts]
```

Replace `create_account`:

```python
async def create_account(session: AsyncSession, payload: AccountCreate, user_id: int) -> AccountWithBalance:
    account = Account(**payload.model_dump(), user_id=user_id)
    session.add(account)
    await session.commit()
    await session.refresh(account)
    # A brand-new account has no transactions yet — no need to query.
    return _to_read(account, Decimal("0"))
```

Replace `update_account`:

```python
async def update_account(
    session: AsyncSession, account_id: int, payload: AccountUpdate, user_id: int
) -> AccountWithBalance:
    account = await get_owned_or_404(session, Account, account_id, user_id, detail="Account not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    await session.commit()
    await session.refresh(account)
    balances = await _account_balances(session)
    return _to_read(account, balances.get(account.id, Decimal("0")))
```

Replace `delete_account`:

```python
async def delete_account(session: AsyncSession, account_id: int, user_id: int) -> None:
    account = await get_owned_or_404(session, Account, account_id, user_id, detail="Account not found")
    await session.delete(account)
    await session.commit()
```

Leave `_account_balances` and `_to_read` untouched — `_account_balances`
still scans every `Transaction` row, not just this user's, but since each
`account_id` it groups by is a globally-unique primary key belonging to
exactly one account (and therefore exactly one user), looking up
`balances.get(account.id, ...)` for one of *this* user's own account ids
can never return another user's balance. This is safe today but will be
tightened for efficiency (not correctness) once `Transaction` itself gets
a `user_id` column in the Part 2 plan — do not attempt that here, it's out
of this task's scope.

- [ ] **Step 4: Wire the router**

Modify `backend/app/api/routes/accounts.py` — replace the whole file:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.account import AccountCreate, AccountUpdate, AccountWithBalance
from app.services.account_service import create_account, delete_account, list_accounts, update_account

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountWithBalance])
async def read_accounts(
    include_archived: bool = False,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[AccountWithBalance]:
    return await list_accounts(session, include_archived, current_user.id)


@router.post("", response_model=AccountWithBalance, status_code=201)
async def create_account_route(
    payload: AccountCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AccountWithBalance:
    return await create_account(session, payload, current_user.id)


@router.patch("/{account_id}", response_model=AccountWithBalance)
async def update_account_route(
    account_id: int,
    payload: AccountUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AccountWithBalance:
    return await update_account(session, account_id, payload, current_user.id)


@router.delete("/{account_id}", status_code=204)
async def delete_account_route(
    account_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    await delete_account(session, account_id, current_user.id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_accounts.py -v`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS — every other test file's `account_id` fixture already
creates its account through the now-authenticated `client` fixture, so
nothing else should break.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/account_service.py backend/app/api/routes/accounts.py backend/tests/test_accounts.py
git commit -m "Изолировать accounts по пользователю"
```

---

## Task 6: Wire `categories`

**Files:**
- Modify: `backend/app/api/routes/categories.py`
- Modify: `backend/tests/test_categories.py`

**Interfaces:**
- Consumes: `get_current_user`, `scoped`, `get_owned_or_404`.
- Produces: no service layer exists for categories (queries live directly
  in the route file, as before) — later tasks that touch categories
  (Part 2's transactions, Part 3's reports/dashboard) must query
  `Category` scoped by `user_id` the same way.

- [ ] **Step 1: Write the failing isolation test**

Append to `backend/tests/test_categories.py`:

```python
from tests.helpers import auth_headers, register_user


async def test_user_a_cannot_see_user_bs_custom_category(client):
    b_tokens = await register_user(client, "catb@example.com")
    b_category = (
        await client.post(
            "/categories",
            json={"name": "B's Category", "kind": "expense", "color": "#e34948"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    a_categories = (await client.get("/categories")).json()
    assert all(c["id"] != b_category["id"] for c in a_categories)


async def test_user_a_cannot_update_user_bs_category(client):
    b_tokens = await register_user(client, "catb2@example.com")
    b_category = (
        await client.post(
            "/categories",
            json={"name": "B's Category", "kind": "expense", "color": "#e34948"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    resp = await client.patch(f"/categories/{b_category['id']}", json={"name": "Hijacked"})
    assert resp.status_code == 404


async def test_user_a_cannot_delete_user_bs_category(client):
    b_tokens = await register_user(client, "catb3@example.com")
    b_category = (
        await client.post(
            "/categories",
            json={"name": "B's Category", "kind": "expense", "color": "#e34948"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    resp = await client.delete(f"/categories/{b_category['id']}")
    assert resp.status_code == 404


async def test_user_a_cannot_nest_under_user_bs_category(client):
    """A's new subcategory must not be allowed to point parent_id at a
    category A doesn't own — that would leak the fact that the id exists
    (or worse, actually attach to it) if _validate_parent used a bare
    session.get instead of an owner-scoped lookup."""
    b_tokens = await register_user(client, "catb4@example.com")
    b_category = (
        await client.post(
            "/categories",
            json={"name": "B's Category", "kind": "expense", "color": "#e34948"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    resp = await client.post(
        "/categories", json={"name": "Sneaky", "kind": "expense", "color": "#e34948", "parent_id": b_category["id"]}
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_categories.py -v -k user_a`
Expected: FAIL — categories aren't scoped yet.

- [ ] **Step 3: Wire the router**

Modify `backend/app/api/routes/categories.py` — replace the whole file:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.category import Category
from app.models.enums import CategoryKind
from app.models.transaction import Transaction, TransactionSplit
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.services.scoped import get_owned_or_404, scoped

router = APIRouter(prefix="/categories", tags=["categories"])


async def _validate_parent(
    session: AsyncSession, parent_id: int, kind: CategoryKind, category_id: int | None, user_id: int
) -> None:
    """Subcategories are one level deep only: a parent must itself be
    top-level, must share the child's kind (an expense category can't
    nest under an income one, or vice versa), and must belong to the same
    user — a nonexistent-or-not-yours parent_id is rejected the same way
    (400, "not found") either way, so this never confirms someone else's
    category id exists."""
    if parent_id == category_id:
        raise HTTPException(status_code=400, detail="A category cannot be its own parent")
    result = await session.execute(select(Category).where(Category.id == parent_id, Category.user_id == user_id))
    parent = result.scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=400, detail="Parent category not found")
    if parent.parent_id is not None:
        raise HTTPException(status_code=400, detail="Subcategories can only be one level deep")
    if parent.kind != kind:
        raise HTTPException(status_code=400, detail="A subcategory must have the same kind as its parent")


@router.get("", response_model=list[CategoryRead])
async def list_categories(
    kind: CategoryKind | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[Category]:
    stmt = scoped(select(Category), Category, current_user.id).order_by(Category.sort_order)
    if kind is not None:
        stmt = stmt.where(Category.kind == kind)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=CategoryRead, status_code=201)
async def create_category(
    payload: CategoryCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Category:
    if payload.parent_id is not None:
        await _validate_parent(session, payload.parent_id, payload.kind, category_id=None, user_id=current_user.id)
    category = Category(**payload.model_dump(), is_default=False, user_id=current_user.id)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Category:
    category = await get_owned_or_404(session, Category, category_id, current_user.id, detail="Category not found")
    updates = payload.model_dump(exclude_unset=True)
    if "parent_id" in updates and updates["parent_id"] is not None:
        await _validate_parent(session, updates["parent_id"], category.kind, category_id=category_id, user_id=current_user.id)
        has_children = (
            await session.execute(select(Category.id).where(Category.parent_id == category_id).limit(1))
        ).first()
        if has_children is not None:
            raise HTTPException(status_code=400, detail="A category with subcategories cannot become a subcategory itself")
    for field, value in updates.items():
        setattr(category, field, value)
    await session.commit()
    await session.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    category = await get_owned_or_404(session, Category, category_id, current_user.id, detail="Category not found")
    if category.is_default:
        # A default (seeded) category can be removed once it's unused — but
        # never while transactions still point at it, or a whole year's
        # worth of history would silently lose its category (the FK is
        # ON DELETE SET NULL, so nothing would error, it would just vanish
        # from every report). A custom category has no such guard: the user
        # created it and can freely delete it, same as before.
        has_transaction = (
            await session.execute(select(Transaction.id).where(Transaction.category_id == category_id).limit(1))
        ).first()
        has_split = (
            await session.execute(select(TransactionSplit.id).where(TransactionSplit.category_id == category_id).limit(1))
        ).first()
        if has_transaction is not None or has_split is not None:
            raise HTTPException(
                status_code=400, detail="Default categories can only be deleted once they have no transactions"
            )
    await session.delete(category)
    await session.commit()
```

(The `has_transaction`/`has_split` checks stay unfiltered by `user_id` —
same "globally-unique id" reasoning as `_account_balances` in Task 5:
`category_id` uniquely identifies one row owned by exactly one user, so an
unfiltered check against it can't reference another user's transactions.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_categories.py -v`
Expected: PASS — all tests in the file.

- [ ] **Step 5: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/categories.py backend/tests/test_categories.py
git commit -m "Изолировать categories по пользователю"
```

---

## Task 7: Wire `tags`

**Files:**
- Modify: `backend/app/api/routes/tags.py`
- Modify: `backend/tests/test_tags.py`

**Interfaces:**
- Consumes: `get_current_user`, `scoped`, `get_owned_or_404`.
- Produces: no service layer (as before) — tag lookups elsewhere
  (transactions, in the Part 2 plan) must filter by `user_id` too.

- [ ] **Step 1: Write the failing isolation test**

Append to `backend/tests/test_tags.py`:

```python
from tests.helpers import auth_headers, register_user


async def test_user_a_cannot_see_user_bs_tags(client):
    b_tokens = await register_user(client, "tagb@example.com")
    await client.post("/tags", json={"name": "b-only"}, headers=auth_headers(b_tokens["access_token"]))

    a_tags = (await client.get("/tags")).json()
    assert all(t["name"] != "b-only" for t in a_tags)


async def test_user_a_and_b_can_each_have_a_tag_with_the_same_name(client):
    """Tag names are unique per-user now, not globally — two different
    users independently creating "groceries" must not collide."""
    b_tokens = await register_user(client, "tagb2@example.com")

    a_tag = (await client.post("/tags", json={"name": "groceries"})).json()
    b_tag = (
        await client.post("/tags", json={"name": "groceries"}, headers=auth_headers(b_tokens["access_token"]))
    ).json()

    assert a_tag["id"] != b_tag["id"]
    assert a_tag["name"] == b_tag["name"] == "groceries"


async def test_user_a_cannot_delete_user_bs_tag(client):
    b_tokens = await register_user(client, "tagb3@example.com")
    b_tag = (
        await client.post("/tags", json={"name": "b-only"}, headers=auth_headers(b_tokens["access_token"]))
    ).json()

    resp = await client.delete(f"/tags/{b_tag['id']}")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_tags.py -v -k user_a`
Expected: FAIL.

- [ ] **Step 3: Wire the router**

Modify `backend/app/api/routes/tags.py` — replace the whole file:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.tag import Tag
from app.models.user import User
from app.schemas.tag import TagCreate, TagRead
from app.services.scoped import get_owned_or_404, scoped

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagRead])
async def list_tags(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> list[Tag]:
    stmt = scoped(select(Tag), Tag, current_user.id).order_by(Tag.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=TagRead, status_code=201)
async def create_tag(
    payload: TagCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Tag:
    # Case-insensitive dedup within this user's own tags — the frontend's
    # tag picker creates tags on the fly as the user types, so "Georgia"
    # and "georgia" typed on two different transactions should end up as
    # the same tag, not two, but that dedup is per-user, not global.
    name = payload.name.strip()
    existing = await session.execute(
        select(Tag).where(func.lower(Tag.name) == name.lower(), Tag.user_id == current_user.id)
    )
    tag = existing.scalar_one_or_none()
    if tag is not None:
        return tag
    tag = Tag(name=name, user_id=current_user.id)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    tag = await get_owned_or_404(session, Tag, tag_id, current_user.id, detail="Tag not found")
    await session.delete(tag)
    await session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_tags.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/tags.py backend/tests/test_tags.py
git commit -m "Изолировать tags по пользователю (уникальность имени теперь per-user)"
```

---

## Task 8: Wire `budgets`

**Files:**
- Modify: `backend/app/services/budget_service.py`
- Modify: `backend/app/api/routes/budgets.py`
- Modify: `backend/tests/test_budgets.py`

**Interfaces:**
- Consumes: `get_current_user`, `scoped`, `get_owned_or_404`.
- Produces: `list_budgets(session, user_id)`, `create_budget(session,
  payload, user_id)`, `update_budget(session, budget_id, payload,
  user_id)`, `delete_budget(session, budget_id, user_id)`,
  `get_budget_status(session, year, month, user_id)`.

- [ ] **Step 1: Write the failing isolation test**

Append to `backend/tests/test_budgets.py`:

```python
from tests.helpers import auth_headers, register_user


async def test_user_a_cannot_see_user_bs_budget(client, categories):
    b_tokens = await register_user(client, "budgetb@example.com")
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")

    await client.post(
        "/budgets",
        json={"category_id": b_groceries, "monthly_limit": "500.00"},
        headers=auth_headers(b_tokens["access_token"]),
    )

    a_budgets = (await client.get("/budgets")).json()
    assert a_budgets == []


async def test_user_a_cannot_update_user_bs_budget(client):
    b_tokens = await register_user(client, "budgetb2@example.com")
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")
    b_budget = (
        await client.post(
            "/budgets",
            json={"category_id": b_groceries, "monthly_limit": "500.00"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    resp = await client.patch(f"/budgets/{b_budget['id']}", json={"monthly_limit": "1.00"})
    assert resp.status_code == 404


async def test_user_a_and_b_can_each_budget_their_own_groceries_category(client):
    """Budget.category_id is globally unique (one budget per category
    row), and each user has their own Groceries category row after the
    per-user seeding change — so this must not collide."""
    b_tokens = await register_user(client, "budgetb3@example.com")
    a_categories = (await client.get("/categories")).json()
    a_groceries = next(c["id"] for c in a_categories if c["name"] == "Groceries")
    b_categories = (await client.get("/categories", headers=auth_headers(b_tokens["access_token"]))).json()
    b_groceries = next(c["id"] for c in b_categories if c["name"] == "Groceries")

    a_resp = await client.post("/budgets", json={"category_id": a_groceries, "monthly_limit": "300.00"})
    b_resp = await client.post(
        "/budgets",
        json={"category_id": b_groceries, "monthly_limit": "400.00"},
        headers=auth_headers(b_tokens["access_token"]),
    )
    assert a_resp.status_code == 201
    assert b_resp.status_code == 201
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_budgets.py -v -k "user_a"`
Expected: FAIL.

- [ ] **Step 3: Wire the service**

Modify `backend/app/services/budget_service.py` — add the import:

```python
from app.services.scoped import get_owned_or_404, scoped
```

Replace `list_budgets`:

```python
async def list_budgets(session: AsyncSession, user_id: int) -> list[Budget]:
    stmt = scoped(select(Budget), Budget, user_id).options(*_EAGER).join(Category).order_by(Category.sort_order)
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

Replace `create_budget`:

```python
async def create_budget(session: AsyncSession, payload: BudgetCreate, user_id: int) -> Budget:
    category = await get_owned_or_404(session, Category, payload.category_id, user_id, detail="Category not found")
    if category.kind != CategoryKind.EXPENSE:
        raise HTTPException(status_code=400, detail="Budgets can only be set on expense categories")

    existing = await session.execute(select(Budget).where(Budget.category_id == payload.category_id))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=f"'{category.name}' already has a budget")

    budget = Budget(category_id=payload.category_id, monthly_limit=payload.monthly_limit, user_id=user_id)
    session.add(budget)
    await session.commit()
    refreshed = await session.execute(select(Budget).options(*_EAGER).where(Budget.id == budget.id))
    return refreshed.scalar_one()
```

(`category.py`'s `get_owned_or_404` replaces the old bare `session.get` —
a budget can only ever be created against a category *this user* owns.
The subsequent `existing = ...` duplicate-budget check stays unfiltered by
user, same "globally-unique category id" reasoning used throughout this
plan.)

Replace `update_budget` and `delete_budget`:

```python
async def update_budget(session: AsyncSession, budget_id: int, payload: BudgetUpdate, user_id: int) -> Budget:
    budget = await get_owned_or_404(session, Budget, budget_id, user_id, detail="Budget not found")
    budget.monthly_limit = payload.monthly_limit
    await session.commit()
    refreshed = await session.execute(select(Budget).options(*_EAGER).where(Budget.id == budget_id))
    return refreshed.scalar_one()


async def delete_budget(session: AsyncSession, budget_id: int, user_id: int) -> None:
    budget = await get_owned_or_404(session, Budget, budget_id, user_id, detail="Budget not found")
    await session.delete(budget)
    await session.commit()
```

Replace `get_budget_status`'s first line (`budgets = await list_budgets(session)`) with:

```python
async def get_budget_status(session: AsyncSession, year: int, month: int, user_id: int) -> BudgetStatusResponse:
    start, end = _month_bounds(year, month)

    budgets = await list_budgets(session, user_id)
```

(Everything else in `get_budget_status` operates on `budgets` — already
scoped — and on `Transaction`/`TransactionSplit` rows joined by
`category_id`, which stay unfiltered by user for the same
globally-unique-id reason as everywhere else in this plan; leave the rest
of the function body untouched.)

- [ ] **Step 4: Wire the router**

Modify `backend/app/api/routes/budgets.py` — replace the whole file:

```python
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.budget import Budget
from app.models.user import User
from app.schemas.budget import BudgetCreate, BudgetRead, BudgetStatusResponse, BudgetUpdate
from app.services.budget_service import create_budget, delete_budget, get_budget_status, list_budgets, update_budget

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _to_read(budget: Budget) -> BudgetRead:
    return BudgetRead(
        id=budget.id,
        category_id=budget.category_id,
        category_name=budget.category.name,
        category_color=budget.category.color,
        category_icon=budget.category.icon,
        monthly_limit=budget.monthly_limit,
    )


@router.get("", response_model=list[BudgetRead])
async def read_budgets(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> list[BudgetRead]:
    return [_to_read(budget) for budget in await list_budgets(session, current_user.id)]


@router.get("/status", response_model=BudgetStatusResponse)
async def read_budget_status(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> BudgetStatusResponse:
    return await get_budget_status(session, year, month, current_user.id)


@router.post("", response_model=BudgetRead, status_code=201)
async def create_budget_route(
    payload: BudgetCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> BudgetRead:
    return _to_read(await create_budget(session, payload, current_user.id))


@router.patch("/{budget_id}", response_model=BudgetRead)
async def update_budget_route(
    budget_id: int,
    payload: BudgetUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> BudgetRead:
    return _to_read(await update_budget(session, budget_id, payload, current_user.id))


@router.delete("/{budget_id}", status_code=204)
async def delete_budget_route(
    budget_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    await delete_budget(session, budget_id, current_user.id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_budgets.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/budget_service.py backend/app/api/routes/budgets.py backend/tests/test_budgets.py
git commit -m "Изолировать budgets по пользователю"
```

---

## Task 9: Wire `goals`

**Files:**
- Modify: `backend/app/services/goal_service.py`
- Modify: `backend/app/api/routes/goals.py`
- Modify: `backend/tests/test_goals.py`

**Interfaces:**
- Consumes: `get_current_user`, `scoped`, `get_owned_or_404`.
- Produces: `list_goals(session, user_id)`, `create_goal(session, payload,
  user_id)`, `update_goal(session, goal_id, payload, user_id)`,
  `delete_goal(session, goal_id, user_id)`, `add_contribution(session,
  goal_id, payload, user_id)`.

- [ ] **Step 1: Write the failing isolation test**

Append to `backend/tests/test_goals.py`:

```python
from tests.helpers import auth_headers, register_user


async def test_user_a_cannot_see_user_bs_goal(client):
    b_tokens = await register_user(client, "goalb@example.com")
    await client.post(
        "/goals",
        json={"name": "B's Goal", "target_amount": "1000.00"},
        headers=auth_headers(b_tokens["access_token"]),
    )

    a_goals = (await client.get("/goals")).json()
    assert a_goals == []


async def test_user_a_cannot_update_or_delete_user_bs_goal(client):
    b_tokens = await register_user(client, "goalb2@example.com")
    b_goal = (
        await client.post(
            "/goals",
            json={"name": "B's Goal", "target_amount": "1000.00"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    update_resp = await client.patch(f"/goals/{b_goal['id']}", json={"name": "Hijacked"})
    assert update_resp.status_code == 404

    delete_resp = await client.delete(f"/goals/{b_goal['id']}")
    assert delete_resp.status_code == 404


async def test_user_a_cannot_contribute_to_user_bs_goal(client):
    b_tokens = await register_user(client, "goalb3@example.com")
    b_goal = (
        await client.post(
            "/goals",
            json={"name": "B's Goal", "target_amount": "1000.00"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()

    resp = await client.post(
        f"/goals/{b_goal['id']}/contributions", json={"amount": "50.00", "date": "2026-01-15"}
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_goals.py -v -k user_a`
Expected: FAIL.

- [ ] **Step 3: Wire the service**

Modify `backend/app/services/goal_service.py`. Add the import:

```python
from app.services.scoped import get_owned_or_404, scoped
```

Replace `_SELECT_WITH_TOTAL`'s definition to not hardcode ordering by a
column alone (it already doesn't filter by user — scoping is applied by
the caller, same pattern as `budget_service.list_budgets`), and update the
three functions that use it. Replace `_read_one`, `list_goals`,
`create_goal`, `update_goal`, `delete_goal`, `add_contribution`:

```python
async def _read_one(session: AsyncSession, goal_id: int, user_id: int) -> GoalRead:
    stmt = scoped(_SELECT_WITH_TOTAL, Goal, user_id).where(Goal.id == goal_id)
    row = (await session.execute(stmt)).one()
    return _to_read(row)


async def list_goals(session: AsyncSession, user_id: int) -> list[GoalRead]:
    stmt = scoped(_SELECT_WITH_TOTAL, Goal, user_id)
    rows = (await session.execute(stmt)).all()
    return [_to_read(row) for row in rows]


async def create_goal(session: AsyncSession, payload: GoalCreate, user_id: int) -> GoalRead:
    goal = Goal(name=payload.name, target_amount=payload.target_amount, target_date=payload.target_date, user_id=user_id)
    session.add(goal)
    await session.commit()
    return GoalRead(
        id=goal.id,
        name=goal.name,
        target_amount=goal.target_amount,
        target_date=goal.target_date,
        current_amount=Decimal("0"),
        remaining=goal.target_amount,
        percent=0.0,
        is_reached=False,
    )


async def update_goal(session: AsyncSession, goal_id: int, payload: GoalUpdate, user_id: int) -> GoalRead:
    goal = await get_owned_or_404(session, Goal, goal_id, user_id, detail="Goal not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)
    await session.commit()
    return await _read_one(session, goal_id, user_id)


async def delete_goal(session: AsyncSession, goal_id: int, user_id: int) -> None:
    goal = await get_owned_or_404(session, Goal, goal_id, user_id, detail="Goal not found")
    await session.delete(goal)
    await session.commit()


async def add_contribution(
    session: AsyncSession, goal_id: int, payload: GoalContributionCreate, user_id: int
) -> GoalRead:
    goal = await get_owned_or_404(session, Goal, goal_id, user_id, detail="Goal not found")
    session.add(GoalContribution(goal_id=goal.id, amount=payload.amount, date=payload.date, note=payload.note))
    await session.commit()
    return await _read_one(session, goal_id, user_id)
```

(Note `_read_one`'s `scoped(_SELECT_WITH_TOTAL, Goal, user_id)` works
because `_SELECT_WITH_TOTAL` selects `Goal.id, Goal.name, ...` columns
directly rather than full `Goal` objects, but `scoped()`'s `.where(model.user_id
== user_id)` still resolves correctly against the same underlying
`Goal` table referenced in that select — this is standard SQLAlchemy
Core behavior, not a special case.)

- [ ] **Step 4: Wire the router**

Modify `backend/app/api/routes/goals.py` — replace the whole file:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.goal import GoalContributionCreate, GoalCreate, GoalRead, GoalUpdate
from app.services.goal_service import add_contribution, create_goal, delete_goal, list_goals, update_goal

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=list[GoalRead])
async def read_goals(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> list[GoalRead]:
    return await list_goals(session, current_user.id)


@router.post("", response_model=GoalRead, status_code=201)
async def create_goal_route(
    payload: GoalCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> GoalRead:
    return await create_goal(session, payload, current_user.id)


@router.patch("/{goal_id}", response_model=GoalRead)
async def update_goal_route(
    goal_id: int,
    payload: GoalUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> GoalRead:
    return await update_goal(session, goal_id, payload, current_user.id)


@router.delete("/{goal_id}", status_code=204)
async def delete_goal_route(
    goal_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    await delete_goal(session, goal_id, current_user.id)


@router.post("/{goal_id}/contributions", response_model=GoalRead, status_code=201)
async def add_contribution_route(
    goal_id: int,
    payload: GoalContributionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> GoalRead:
    return await add_contribution(session, goal_id, payload, current_user.id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_goals.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/goal_service.py backend/app/api/routes/goals.py backend/tests/test_goals.py
git commit -m "Изолировать goals по пользователю"
```

---

## Task 10: Wire `recurring`

**Files:**
- Modify: `backend/app/services/recurring_service.py`
- Modify: `backend/app/api/routes/recurring.py`
- Create: `backend/tests/test_recurring.py`

**Interfaces:**
- Consumes: `get_current_user`, `scoped`, `get_owned_or_404`.
- Produces: `list_recurring(session, user_id)`, `create_recurring(session,
  payload, user_id)`, `update_recurring(session, recurring_id, payload,
  user_id)`, `delete_recurring(session, recurring_id, user_id)`,
  `post_recurring(session, recurring_id, user_id)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_recurring.py` (no test file existed for this
router before):

```python
"""Recurring transaction templates: CRUD, posting, plus per-user isolation."""
from tests.helpers import auth_headers, register_user


def _payload(account_id: int, **overrides) -> dict:
    payload = {
        "account_id": account_id,
        "type": "expense",
        "amount": "9.99",
        "description": "Streaming subscription",
        "frequency": "monthly",
        "anchor_date": "2026-01-01",
    }
    payload.update(overrides)
    return payload


async def test_create_and_list_recurring(client, account_id):
    resp = await client.post("/recurring", json=_payload(account_id))
    assert resp.status_code == 201
    listed = await client.get("/recurring")
    assert len(listed.json()) == 1


async def test_post_recurring_creates_a_transaction(client, account_id):
    created = (await client.post("/recurring", json=_payload(account_id))).json()
    resp = await client.post(f"/recurring/{created['id']}/post")
    assert resp.status_code == 201
    assert resp.json()["last_posted_date"] is not None


async def test_user_a_cannot_see_user_bs_recurring(client, account_id):
    b_tokens = await register_user(client, "recb@example.com")
    b_account = (
        await client.post(
            "/accounts",
            json={"name": "B's", "type": "checking", "currency": "USD"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()
    await client.post("/recurring", json=_payload(b_account["id"]), headers=auth_headers(b_tokens["access_token"]))

    a_list = (await client.get("/recurring")).json()
    assert a_list == []


async def test_user_a_cannot_update_delete_or_post_user_bs_recurring(client):
    b_tokens = await register_user(client, "recb2@example.com")
    b_account = (
        await client.post(
            "/accounts",
            json={"name": "B's", "type": "checking", "currency": "USD"},
            headers=auth_headers(b_tokens["access_token"]),
        )
    ).json()
    b_recurring = (
        await client.post(
            "/recurring", json=_payload(b_account["id"]), headers=auth_headers(b_tokens["access_token"])
        )
    ).json()

    assert (await client.patch(f"/recurring/{b_recurring['id']}", json={"amount": "1.00"})).status_code == 404
    assert (await client.post(f"/recurring/{b_recurring['id']}/post")).status_code == 404
    assert (await client.delete(f"/recurring/{b_recurring['id']}")).status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_recurring.py -v`
Expected: `test_create_and_list_recurring` and `test_post_recurring_creates_a_transaction`
PASS already (the recurring router works today, it's just unscoped —
these two tests don't test isolation, only basic behavior). The two
`test_user_a_cannot_...` tests FAIL — that's the actual red state this
task fixes. Confirm this split matches what you see and report if it
doesn't (e.g. if a basic test fails for an unrelated reason, that's worth
flagging before proceeding).

- [ ] **Step 3: Wire the service**

Modify `backend/app/services/recurring_service.py`. Add the import:

```python
from app.services.scoped import get_owned_or_404, scoped
```

Modify `_ensure_category_matches_type` to take and check ownership:

```python
async def _ensure_category_matches_type(
    session: AsyncSession, category_id: int | None, transaction_type: TransactionType, user_id: int
) -> None:
    if category_id is None:
        return
    expected_kind = _TYPE_TO_CATEGORY_KIND.get(transaction_type)
    category = await get_owned_or_404(session, Category, category_id, user_id, detail="Category not found")
    if expected_kind is not None and category.kind != expected_kind:
        raise HTTPException(
            status_code=400,
            detail=f"Category '{category.name}' is a {category.kind.value} category and cannot be used for a {transaction_type.value} recurring transaction",
        )
```

(This changes a "400 category not found" into a "404 Category not found"
for the not-owned case — acceptable and consistent with how every other
owner-scoped lookup in this plan behaves; a category that doesn't belong
to you is treated as not existing.)

Replace `_get_or_404`, `list_recurring`, `create_recurring`,
`update_recurring`, `delete_recurring`, `post_recurring`:

```python
async def _get_or_404(session: AsyncSession, recurring_id: int, user_id: int) -> RecurringTransaction:
    result = await session.execute(
        select(RecurringTransaction)
        .options(*_EAGER)
        .where(RecurringTransaction.id == recurring_id, RecurringTransaction.user_id == user_id)
    )
    recurring = result.scalar_one_or_none()
    if recurring is None:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")
    return recurring


async def list_recurring(session: AsyncSession, user_id: int) -> list[RecurringTransactionRead]:
    stmt = scoped(select(RecurringTransaction), RecurringTransaction, user_id).options(*_EAGER).order_by(
        RecurringTransaction.id
    )
    result = await session.execute(stmt)
    return [_to_read(row) for row in result.scalars().all()]


async def create_recurring(
    session: AsyncSession, payload: RecurringTransactionCreate, user_id: int
) -> RecurringTransactionRead:
    await _ensure_category_matches_type(session, payload.category_id, payload.type, user_id)
    recurring = RecurringTransaction(**payload.model_dump(), user_id=user_id)
    session.add(recurring)
    await session.commit()
    return _to_read(await _get_or_404(session, recurring.id, user_id))


async def update_recurring(
    session: AsyncSession, recurring_id: int, payload: RecurringTransactionUpdate, user_id: int
) -> RecurringTransactionRead:
    recurring = await _get_or_404(session, recurring_id, user_id)
    updates = payload.model_dump(exclude_unset=True)
    effective_type = updates.get("type", recurring.type)
    effective_category_id = updates.get("category_id", recurring.category_id)
    await _ensure_category_matches_type(session, effective_category_id, effective_type, user_id)
    for field, value in updates.items():
        setattr(recurring, field, value)
    await session.commit()
    return _to_read(await _get_or_404(session, recurring_id, user_id))


async def delete_recurring(session: AsyncSession, recurring_id: int, user_id: int) -> None:
    recurring = await get_owned_or_404(
        session, RecurringTransaction, recurring_id, user_id, detail="Recurring transaction not found"
    )
    await session.delete(recurring)
    await session.commit()


async def post_recurring(session: AsyncSession, recurring_id: int, user_id: int) -> RecurringTransactionRead:
    """Creates a real Transaction from the template, dated today, and moves
    last_posted_date forward — the only thing that advances the schedule."""
    recurring = await _get_or_404(session, recurring_id, user_id)
    today = date_.today()

    session.add(
        Transaction(
            account_id=recurring.account_id,
            category_id=recurring.category_id,
            transfer_account_id=recurring.transfer_account_id,
            type=recurring.type,
            amount=recurring.amount,
            description=recurring.description,
            merchant=recurring.merchant,
            notes=recurring.notes,
            date=today,
        )
    )
    recurring.last_posted_date = today
    await session.commit()
    return _to_read(await _get_or_404(session, recurring_id, user_id))
```

- [ ] **Step 4: Wire the router**

Modify `backend/app/api/routes/recurring.py` — replace the whole file:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.recurring import RecurringTransactionCreate, RecurringTransactionRead, RecurringTransactionUpdate
from app.services.recurring_service import (
    create_recurring,
    delete_recurring,
    list_recurring,
    post_recurring,
    update_recurring,
)

router = APIRouter(prefix="/recurring", tags=["recurring"])


@router.get("", response_model=list[RecurringTransactionRead])
async def read_recurring(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> list[RecurringTransactionRead]:
    return await list_recurring(session, current_user.id)


@router.post("", response_model=RecurringTransactionRead, status_code=201)
async def create_recurring_route(
    payload: RecurringTransactionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringTransactionRead:
    return await create_recurring(session, payload, current_user.id)


@router.patch("/{recurring_id}", response_model=RecurringTransactionRead)
async def update_recurring_route(
    recurring_id: int,
    payload: RecurringTransactionUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringTransactionRead:
    return await update_recurring(session, recurring_id, payload, current_user.id)


@router.delete("/{recurring_id}", status_code=204)
async def delete_recurring_route(
    recurring_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    await delete_recurring(session, recurring_id, current_user.id)


@router.post("/{recurring_id}/post", response_model=RecurringTransactionRead, status_code=201)
async def post_recurring_route(
    recurring_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringTransactionRead:
    return await post_recurring(session, recurring_id, current_user.id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_recurring.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/recurring_service.py backend/app/api/routes/recurring.py backend/tests/test_recurring.py
git commit -m "Изолировать recurring transactions по пользователю"
```

---

## Task 11: Wire `settings`

**Files:**
- Modify: `backend/app/services/settings_service.py`
- Modify: `backend/app/api/routes/settings.py`
- Create: `backend/tests/test_settings.py`

**Interfaces:**
- Consumes: `get_current_user`.
- Produces: `get_or_create_app_settings(session, user_id) -> AppSettings`
  — later plans (Part 3's insights/dashboard/net_worth, which all read
  the caller's currency/thresholds) call this with the caller's
  `user_id`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_settings.py` (no test file existed for this
router before):

```python
"""App settings: one row per user (currency, alert thresholds), plus
per-user isolation."""
from tests.helpers import auth_headers, register_user


async def test_get_settings_returns_the_seeded_defaults(client):
    resp = await client.get("/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "USD"


async def test_update_settings_persists_a_partial_change(client):
    resp = await client.patch("/settings", json={"currency": "EUR"})
    assert resp.status_code == 200
    assert resp.json()["currency"] == "EUR"

    refetched = await client.get("/settings")
    assert refetched.json()["currency"] == "EUR"


async def test_user_a_changing_currency_does_not_affect_user_b(client):
    b_tokens = await register_user(client, "setb@example.com")

    await client.patch("/settings", json={"currency": "EUR"})

    b_settings = await client.get("/settings", headers=auth_headers(b_tokens["access_token"]))
    assert b_settings.json()["currency"] == "USD"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_settings.py -v`
Expected: the first two tests likely already pass by coincidence (the
route works, just unscoped); `test_user_a_changing_currency_does_not_affect_user_b`
FAILS — both users currently share whatever settings row `get_or_create_app_settings`
finds.

- [ ] **Step 3: Wire the service**

Modify `backend/app/services/settings_service.py` — replace the whole file:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import AppSettings


async def get_or_create_app_settings(session: AsyncSession, user_id: int) -> AppSettings:
    """One row per user — get-or-create so callers never hit a missing
    row even if registration's seeding hasn't run for some reason (e.g. a
    row manually deleted). In normal operation this row is created once,
    at registration (see db/seed.py:seed_default_app_settings, called from
    services/auth_service.py:register)."""
    result = await session.execute(select(AppSettings).where(AppSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = AppSettings(user_id=user_id)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings
```

- [ ] **Step 4: Wire the router**

Modify `backend/app/api/routes/settings.py` — replace the whole file:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.settings import AppSettings
from app.models.user import User
from app.schemas.settings import AppSettingsRead, AppSettingsUpdate
from app.services.settings_service import get_or_create_app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=AppSettingsRead)
async def read_settings(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> AppSettings:
    return await get_or_create_app_settings(session, current_user.id)


@router.patch("", response_model=AppSettingsRead)
async def update_settings(
    payload: AppSettingsUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AppSettings:
    settings = await get_or_create_app_settings(session, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    await session.commit()
    await session.refresh(settings)
    return settings
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_settings.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS — this is the last task in this plan, so this run should
show every test in the suite green, with no `user_id`-related warnings.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/settings_service.py backend/app/api/routes/settings.py backend/tests/test_settings.py
git commit -m "Изолировать app settings по пользователю"
```

---

## Plan Self-Review Notes

- **Spec coverage:** Implements the "Authorization / data isolation"
  section's chosen approach (scoped-query helper) for 7 of the ~13 tables
  the spec lists, plus the per-user category/settings seeding piece of
  "Auth flow" that the Auth Foundation plan explicitly deferred here. The
  remaining tables (`transactions`, `assets`, `asset_valuations`, and the
  crypto tables) are Part 2; the read-only aggregation routers and the
  final `NOT NULL` migration are Part 3. `crypto_portfolios` — a table the
  original spec's table list omitted but that clearly needs isolation
  (users create named portfolios directly) — is noted here for Part 2 to
  pick up; not this plan's concern since it doesn't touch crypto at all.
- **Type/interface consistency:** Every service function's new `user_id:
  int` parameter is threaded consistently between its route and its
  tests; `scoped()`/`get_owned_or_404()` are used with matching import
  paths and signatures in every task from Task 5 onward.
- **No placeholders:** every step contains complete, real code.

---

## Next Plans

**Part 2 (transactions, assets, crypto):** adds `user_id` to
`transactions`, `assets`, `asset_valuations`, `crypto_portfolios`,
`crypto_holdings`, `crypto_transactions`; wires `routes/transactions.py`
(the most complex router — splits, tags, transfers), `routes/assets.py`,
and `routes/crypto.py`; adds the CoinGecko price cache from the spec.

**Part 3 (read-only aggregation + cutover):** wires `dashboard`,
`net_worth`, `cash_flow`, `reports`, `advice`, `insights`, `backup`
(all of which query across many tables at once, so they can only be
converted once Part 1 and Part 2 are both done); adds admin-managed users
listing awareness if needed; runs the final migration flipping every
`user_id` column to `NOT NULL` now that every writer sets it; retires
`AURUM_BASIC_AUTH_USER`/`PASSWORD` and nginx's `auth_basic` (coordinated
with whichever plan adds real frontend login screens, since removing
Basic Auth without a working frontend login leaves the web UI unusable).
