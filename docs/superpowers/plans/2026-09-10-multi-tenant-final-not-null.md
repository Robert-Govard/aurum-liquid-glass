# Multi-Tenant Cutover — Final NOT NULL Migration (Part 3C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flip every `user_id` column added across the whole multi-tenant
series (Auth Foundation through the backup self-service rework) from
nullable to `NOT NULL` at the database level, and update every
corresponding SQLAlchemy model to match — closing out the "nullable until
every write path is converted" strategy this entire series has run under,
now that it genuinely is true everywhere (backup/restore, the last holdout,
was fixed in the immediately preceding plan).

**Scope note (explicit, confirmed with the user before writing this plan):**
this is a backend-only, database-schema plan. Retiring
`AURUM_BASIC_AUTH_USER`/`PASSWORD` and nginx's `auth_basic` is explicitly
**deferred**, not part of this plan — investigation found the frontend has
no real JWT login/registration screen yet (`frontend/src/lib/auth.ts` and
`LoginGate.tsx` implement Basic Auth dressed up in JavaScript, not a call to
the backend's already-existing `/auth/*` endpoints). Removing the Basic
Auth gate before a real JWT login screen exists would leave the web app
with **no login prompt at all**. That frontend work is out of this plan's
scope; Basic Auth retirement happens in a later plan, after it.

**Architecture:** One Alembic migration. `upgrade()` first deletes any
pre-existing "orphan" rows (`user_id IS NULL`) from all 14 tables, in
dependency order (children before parents, respecting
`crypto_holdings → crypto_portfolios`'s `ON DELETE RESTRICT`), then runs
`ALTER COLUMN user_id SET NOT NULL` on all 14. Confirmed directly against
the live dev database before writing this plan: the only tables with any
orphan rows today are `accounts` (1), `categories` (17), `app_settings`
(1), and `crypto_portfolios` (1) — pre-multi-tenant seed data that predates
this whole series — and NONE of them are referenced by any row that DOES
have a real `user_id` (verified with direct SQL joins against every FK
relationship), so deleting them is a clean, non-cascading removal with zero
risk to real data. The migration still deletes-then-checks all 14 tables
unconditionally (not just these 4), so it's correct and safe to run against
any other environment's data too, not just this exact dev database's
current state.

Every model's `user_id` column changes from `Mapped[int | None]` +
`nullable=True` to `Mapped[int]` + `nullable=False` (the two `unique=True`
columns — `app_settings`, `crypto_sync_state` — keep `unique=True`,
changing only `nullable`). `settings_service.py`'s
`get_or_create_app_settings` legacy `user_id: int | None = None` bridge —
its own docstring has said "remove it once nothing references the
`user_id=None` path anymore" since Part 2B — is removed in the same task,
confirmed via `grep` that all 8 call sites already pass a real `user_id`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL,
Docker Compose — same stack as the rest of this series; no new
dependencies.

**Spec:** [docs/superpowers/specs/2026-09-08-multi-tenant-backend-design.md](../specs/2026-09-08-multi-tenant-backend-design.md)

## Global Constraints

- Orphan-row deletion happens BEFORE the `NOT NULL` `ALTER COLUMN`s in the
  same migration, in a dependency order that respects every relevant FK
  `ondelete` behavior (verified against the live models — see Task 1).
- `downgrade()` reverses the schema change (`nullable=True` again) but does
  **not** attempt to restore deleted orphan rows — that deletion is a
  deliberate, irreversible data cleanup, not a reversible schema edit, and
  the migration's downgrade docstring says so explicitly.
- No route, service, or schema behavior changes in this plan beyond the
  type-level `int | None` → `int` narrowing on `user_id` parameters/columns
  and the `get_or_create_app_settings` signature simplification — this is
  a schema/type-tightening pass, not a feature change.
- Basic Auth retirement is explicitly OUT of scope (see above) — do not
  touch `docker-compose.yml`'s Basic Auth env vars, `frontend/nginx.conf`,
  or `frontend/docker-entrypoint.d/20-basic-auth.sh` in this plan.

---

## Task 1: Migration + model + settings_service.py cutover

**Files:**
- Create: `backend/alembic/versions/<new_revision>_make_user_id_not_null.py`
- Modify: `backend/app/models/account.py`, `category.py`, `tag.py`,
  `budget.py`, `goal.py`, `recurring.py`, `transaction.py`, `asset.py`
  (2 columns), `crypto.py` (4 columns), `settings.py`
- Modify: `backend/app/services/settings_service.py`
- Modify: `backend/tests/test_settings.py` (or wherever a settings-service
  test file naturally fits — see Step 6) to cover the simplified signature

**Interfaces:**
- Produces: `get_or_create_app_settings(session: AsyncSession, user_id:
  int) -> AppSettings` — `user_id` is no longer optional. Every one of its
  8 existing call sites (`routes/settings.py` x2, `crypto_service.py` x3,
  `backup_service.py` x2, `insights_service.py` x1) already passes a real
  `int`, so no caller needs to change.

- [ ] **Step 1: Confirm the live orphan-row picture one more time before writing the migration**

Run (from the worktree root, against the running dev stack):

```bash
docker compose exec -T db psql -U aurum -d aurum -c "
SELECT 'accounts' t, count(*) FROM accounts WHERE user_id IS NULL
UNION ALL SELECT 'categories', count(*) FROM categories WHERE user_id IS NULL
UNION ALL SELECT 'tags', count(*) FROM tags WHERE user_id IS NULL
UNION ALL SELECT 'budgets', count(*) FROM budgets WHERE user_id IS NULL
UNION ALL SELECT 'goals', count(*) FROM goals WHERE user_id IS NULL
UNION ALL SELECT 'recurring_transactions', count(*) FROM recurring_transactions WHERE user_id IS NULL
UNION ALL SELECT 'transactions', count(*) FROM transactions WHERE user_id IS NULL
UNION ALL SELECT 'assets', count(*) FROM assets WHERE user_id IS NULL
UNION ALL SELECT 'asset_valuations', count(*) FROM asset_valuations WHERE user_id IS NULL
UNION ALL SELECT 'crypto_portfolios', count(*) FROM crypto_portfolios WHERE user_id IS NULL
UNION ALL SELECT 'crypto_holdings', count(*) FROM crypto_holdings WHERE user_id IS NULL
UNION ALL SELECT 'crypto_transactions', count(*) FROM crypto_transactions WHERE user_id IS NULL
UNION ALL SELECT 'app_settings', count(*) FROM app_settings WHERE user_id IS NULL
UNION ALL SELECT 'crypto_sync_state', count(*) FROM crypto_sync_state WHERE user_id IS NULL;
"
```

Expected (as confirmed during this plan's own research): `accounts=1`,
`categories=17`, `app_settings=1`, `crypto_portfolios=1`, everything else
`0`. If the numbers differ (this is a live dev database, not a fixed
fixture), that's fine — the migration in Step 2 handles any of these being
nonzero, not just today's exact values. If you find any NON-zero count in
a table this plan didn't expect to have orphans, stop and re-verify (per
Step 1a below) before proceeding — an unexpected orphan in, say,
`transactions` would mean something wrote a transaction without a
`user_id` sometime after this series' earlier plans were supposed to have
closed that gap, and that's worth understanding before silently deleting
it.

- [ ] **Step 1a: Confirm no real (non-orphan) row references an orphan row**

Run:

```bash
docker compose exec -T db psql -U aurum -d aurum -c "
SELECT 'transactions_ref_orphan_account' t, count(*) FROM transactions WHERE user_id IS NOT NULL AND account_id IN (SELECT id FROM accounts WHERE user_id IS NULL)
UNION ALL SELECT 'transactions_ref_orphan_category', count(*) FROM transactions WHERE user_id IS NOT NULL AND category_id IN (SELECT id FROM categories WHERE user_id IS NULL)
UNION ALL SELECT 'budgets_ref_orphan_category', count(*) FROM budgets WHERE user_id IS NOT NULL AND category_id IN (SELECT id FROM categories WHERE user_id IS NULL)
UNION ALL SELECT 'recurring_ref_orphan_account', count(*) FROM recurring_transactions WHERE user_id IS NOT NULL AND account_id IN (SELECT id FROM accounts WHERE user_id IS NULL)
UNION ALL SELECT 'recurring_ref_orphan_category', count(*) FROM recurring_transactions WHERE user_id IS NOT NULL AND category_id IN (SELECT id FROM categories WHERE user_id IS NULL)
UNION ALL SELECT 'crypto_holdings_ref_orphan_portfolio', count(*) FROM crypto_holdings WHERE user_id IS NOT NULL AND portfolio_id IN (SELECT id FROM crypto_portfolios WHERE user_id IS NULL)
UNION ALL SELECT 'categories_ref_orphan_parent', count(*) FROM categories WHERE user_id IS NOT NULL AND parent_id IN (SELECT id FROM categories WHERE user_id IS NULL);
"
```

Expected: every row `0` (confirmed during this plan's research against
the current dev database). If any count is nonzero, STOP — this would
mean a real, properly-owned row depends on data this migration is about
to delete, and deleting it would silently corrupt that real user's data
(e.g. a transaction losing its category, or worse, a `budgets.category_id`
CASCADE deleting a real user's budget because it happened to reference an
orphan category). Do not proceed past this step until you understand and
resolve any such reference — this is exactly the kind of "irreversible/
destructive operation" this project's own safety rules require pausing on;
report it rather than working around it silently.

- [ ] **Step 2: Write the migration**

Find the current alembic head:

```bash
docker compose exec backend alembic current
```

(Expected: `f91a3d5c7e42` per this plan's own research — confirm it
matches before writing `down_revision`, in case something changed since.)

Create `backend/alembic/versions/<generate-a-real-revision-id>_make_user_id_not_null.py`
(use a random 12-hex-char id in the same style as this series' other
migrations, e.g. via `python -c "import uuid; print(uuid.uuid4().hex[:12])"`):

```python
"""make user_id NOT NULL on every multi-tenant table

Revision ID: <your-generated-id>
Revises: f91a3d5c7e42
Create Date: 2026-09-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '<your-generated-id>'
down_revision: Union[str, None] = 'f91a3d5c7e42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every table this multi-tenant series added a nullable user_id to, in an
# order safe for deleting orphan (user_id IS NULL) rows: children before
# parents, respecting crypto_holdings -> crypto_portfolios's ON DELETE
# RESTRICT (a portfolio can't be deleted while it still has holdings).
# transaction_splits and goal_contributions are deliberately absent here —
# neither has a user_id column of its own (they're reached only through
# their already-listed parent, Transaction/Goal, and cascade-delete
# automatically when it does).
_DELETE_ORDER = [
    "asset_valuations",
    "crypto_transactions",
    "crypto_holdings",
    "crypto_portfolios",
    "budgets",
    "goals",
    "recurring_transactions",
    "transactions",
    "tags",
    "assets",
    "categories",
    "accounts",
    "app_settings",
    "crypto_sync_state",
]


def upgrade() -> None:
    conn = op.get_bind()
    # Pre-multi-tenant rows with no owner (seed/test data from before this
    # whole series began) — see this migration's own plan document for the
    # exact verification queries run against the dev database confirming
    # none of these are referenced by any properly-owned row.
    for table in _DELETE_ORDER:
        conn.execute(sa.text(f"DELETE FROM {table} WHERE user_id IS NULL"))

    for table in _DELETE_ORDER:
        op.alter_column(table, "user_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    # Reverses the schema change only — deleted orphan rows are NOT
    # restored. That deletion was a deliberate, irreversible data cleanup
    # (this migration's whole point), not a reversible schema edit.
    for table in reversed(_DELETE_ORDER):
        op.alter_column(table, "user_id", existing_type=sa.Integer(), nullable=True)
```

- [ ] **Step 3: Verify the migration runs both ways**

Run: `docker compose exec backend alembic upgrade head`, confirm the
orphan counts from Step 1 are now all `0` and every `user_id` column
reports `NOT NULL` (`\d accounts` etc. via `docker compose exec db psql
-U aurum -d aurum -c "\d accounts"`, checking the `Not null` marker),
then `docker compose exec backend alembic downgrade -1`, confirm columns
are nullable again (orphan rows do NOT come back — expected, per the
downgrade's own documented behavior), then `docker compose exec backend
alembic upgrade head` again to leave the database in the final state.

- [ ] **Step 4: Update every model**

Modify `backend/app/models/account.py` — replace:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

with:

```python
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
```

Apply the identical replacement (same old string, same new string) in
`backend/app/models/category.py`, `backend/app/models/tag.py`,
`backend/app/models/budget.py`, `backend/app/models/goal.py`,
`backend/app/models/recurring.py`, `backend/app/models/transaction.py` —
each has exactly one occurrence of this exact line.

Modify `backend/app/models/asset.py` — this file has the SAME line
appearing twice (once in `Asset`, once in `AssetValuation`) — replace
BOTH occurrences with the same `nullable=False`/`Mapped[int]` form shown
above.

Modify `backend/app/models/crypto.py` — this file has the same
single-line form three times (`CryptoPortfolio`, `CryptoHolding`,
`CryptoTransaction`) — replace all three identically. It also has one
multi-line `unique=True` form (`CryptoSyncState`) — replace:

```python
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, unique=True
    )
```

with:

```python
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
```

Modify `backend/app/models/settings.py` — replace the same multi-line
`unique=True` form (in `AppSettings`) identically to the `CryptoSyncState`
change above.

- [ ] **Step 5: Simplify `get_or_create_app_settings`**

Modify `backend/app/services/settings_service.py` — replace the whole
file:

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

(This removes the `user_id: int | None = None` legacy branch entirely —
its own docstring has said "remove it once nothing references the
`user_id=None` path anymore" since Part 2B, and this plan's own research
confirmed via `grep -rn "get_or_create_app_settings" backend/app/` that
all 8 existing call sites already pass a real `int`. Additionally, this
branch is now not just unused but actively broken post-Step-4: it used to
create `AppSettings()` with no `user_id` at all, which would now violate
the new `NOT NULL` constraint.)

- [ ] **Step 6: Run the full backend suite**

Run: `docker compose exec backend pytest -q`
Expected: PASS, same aggregate as before this plan (221 passed, 0 failed,
0 xfailed — this plan changes types/constraints, not behavior, so no
existing test should need updating). If anything fails, it most likely
means a test was directly constructing a model instance without
`user_id` (bypassing the normal API flow) — find and fix that test's
construction rather than reverting the model change, since the whole
point of this plan is that such a construction should no longer be valid
anywhere in the codebase.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/*_make_user_id_not_null.py backend/app/models/account.py backend/app/models/category.py backend/app/models/tag.py backend/app/models/budget.py backend/app/models/goal.py backend/app/models/recurring.py backend/app/models/transaction.py backend/app/models/asset.py backend/app/models/crypto.py backend/app/models/settings.py backend/app/services/settings_service.py
git commit -m "Перевести user_id в NOT NULL на всех таблицах и убрать устаревшую legacy-ветку настроек"
```

---

## Plan Self-Review Notes

- **Spec coverage:** Implements the "final NOT NULL pass" every prior
  plan in this series has referenced in its own "Next Plan" section as
  the eventual cutover point, now that backup/restore (confirmed via this
  plan's own research to be the last unscoped write path) was fixed by
  the immediately preceding plan.
- **Type/interface consistency:** `get_or_create_app_settings`'s
  simplified `user_id: int` signature was checked against all 8 real
  call sites via direct `grep` before this plan was written — none pass
  `None` or omit the argument.
- **No placeholders:** every step contains complete, real code, including
  the full migration file and every model's exact before/after text,
  verified against the actual current file contents read directly from
  the repository (not reconstructed from memory).
- **Safety verification performed BEFORE writing this plan, not assumed:**
  the claim "no real row references an orphan row" was checked with
  actual SQL against the live dev database (see Task 1 Steps 1/1a),
  not asserted from the code alone — a schema-level NOT NULL migration is
  exactly the kind of change where "should be fine" isn't good enough.

---

## Next Plan

**Frontend JWT login/registration UI:** build a real login/registration
screen backed by the backend's already-existing `/auth/register`,
`/auth/login`, `/auth/refresh`, `/auth/logout` endpoints (see
`backend/app/api/routes/auth.py`), replacing `frontend/src/lib/auth.ts`'s
current Basic-Auth-in-JS-clothing implementation. Once real per-user login
gates the SPA itself, a follow-up plan can safely retire
`AURUM_BASIC_AUTH_USER`/`PASSWORD` and nginx's `auth_basic` (see
`docker-compose.yml`, `frontend/nginx.conf`,
`frontend/docker-entrypoint.d/20-basic-auth.sh`) without leaving the app
with no login prompt at all. After that, the originally-requested Android
(Capacitor) app becomes unblocked.
