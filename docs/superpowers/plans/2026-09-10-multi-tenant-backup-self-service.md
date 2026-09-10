# Self-Service Per-User Backup (Part 3B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Aurum's backup/restore feature from an admin-only, instance-wide
operation (exports/wipes/restores every user's data at once) into a
self-service feature any authenticated user can use for just their own data —
closing the last piece of this multi-tenant series that still required an
admin role for an ordinary user-facing feature, and simultaneously fixing
every `xfail`-marked backup round-trip test this series has accumulated
(2 in `test_backup.py`, 3 in `test_crypto.py` — all caused by the exact same
root cause this plan fixes: restore never stamped `user_id`).

**Architecture:** No schema changes. `build_backup(session, user_id)` scopes
every read via `scoped()` (or a join-through-parent for the two child tables
with no `user_id` column of their own — `transaction_splits`,
`goal_contributions`). `restore_backup(session, payload, user_id)` deletes
only the calling user's own rows (never touches another user's data),
reinserts every row from the payload with `user_id` stamped explicitly, and
fixes a real correctness bug the single-tenant version could get away with:
`_reset_sequence` used to bump each table's identity sequence to
`max(payload's own row ids)`, which was safe only because a single-tenant
restore first wiped the *entire* table — with other users' rows now staying
in the table, that same logic could move the sequence *backward* below ids
another user already holds, and a future ordinary `INSERT` by anyone would
then collide with one of that user's existing rows. The fix: always set the
sequence to the table's actual live `MAX(id)` (across every user, including
whatever this restore just inserted) rather than the payload's own max —
provably non-decreasing regardless of how other users' data has grown since
the backup was taken. Both routes switch from `get_current_admin` to
`get_current_user`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Docker
Compose — same stack as the rest of this series; no new dependencies, no
migration.

**Spec:** [docs/superpowers/specs/2026-09-08-multi-tenant-backend-design.md](../specs/2026-09-08-multi-tenant-backend-design.md)

## Global Constraints

- No migration in this plan — every column already exists.
- `restore_backup` must NEVER delete, modify, or read any row belonging to
  a user other than the caller. This is the single most important property
  in this plan — a bug here would let one user destroy another's entire
  financial history.
- Every restored row is stamped with the CALLING user's `user_id`,
  regardless of anything in the payload (the payload schema carries no
  `user_id` field at all — it never has, since a backup is implicitly "one
  user's data").
- `_reset_sequence` must be non-decreasing: it may only ever raise a
  table's sequence to at least its current live `MAX(id)`, never lower it,
  regardless of interleaving with other users' concurrent normal usage.
- `transaction_splits` and `goal_contributions` have no `user_id` column of
  their own — deletion relies on `ON DELETE CASCADE` from their parent
  (`Transaction`/`Goal`, both confirmed cascading in `models/transaction.py`
  and `models/goal.py`); reads scope via a join to the parent.
- `get_or_create_app_settings(session, user_id)` (built in an earlier,
  already-merged plan) replaces the old `session.get(AppSettings, 1)`
  singleton lookup, in both `build_backup` and `restore_backup`.
- `_validate_references` (payload self-consistency checks) is unchanged —
  it validates relationships *within* the uploaded payload itself, which
  has nothing to do with which user is calling.
- Existing, already-merged tests in `test_backup.py`/`test_crypto.py` that
  currently call `promote_current_user_to_admin` before hitting
  `/backup/*` no longer need to (the routes stop requiring admin in this
  plan) — remove that call, not just leave it as harmless dead weight,
  so the tests read accurately once this plan lands.
- The 5 `xfail(strict=True)`-marked tests this series has accumulated for
  this exact bug class (2 in `test_backup.py`, 3 in `test_crypto.py`) must
  have their `@pytest.mark.xfail(...)` decorators removed once this plan's
  restore stamps `user_id` correctly — leaving them `xfail` after they
  start passing would trip `strict=True` into a hard failure anyway, so
  this isn't optional polish.

---

## Task 1: Scope `build_backup` (export) for per-user + wire the export route

**Files:**
- Modify: `backend/app/services/backup_service.py` (only `build_backup`)
- Modify: `backend/app/api/routes/backup.py` (only `export_backup` and its imports)
- Modify: `backend/tests/test_backup.py` (existing tests' admin-promotion calls; one new test)

**Interfaces:**
- Produces: `build_backup(session, user_id) -> BackupPayload` — gains a
  required `user_id: int` parameter.

**Known interim state:** after this task, `import_backup`/`restore_backup`
are UNCHANGED (still admin-gated, still calling the old 1-arg
`restore_backup(session, payload)`) — this task only touches export. Any
existing test that calls `/backup/import` still needs
`promote_current_user_to_admin` until Task 2 lands; only remove that call
from tests that ONLY exercise export.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_backup.py`:

```python
async def test_export_only_includes_the_callers_own_data(client: AsyncClient, account_id, categories):
    from tests.helpers import auth_headers, register_user

    b_tokens = await register_user(client, "backupb@example.com")
    await client.post(
        "/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
        headers=auth_headers(b_tokens["access_token"]),
    )

    payload = (await client.get("/backup/export")).json()
    account_names = {a["name"] for a in payload["accounts"]}
    assert "B Wallet" not in account_names
```

Note: this test calls `GET /backup/export` with the default `client`
(no admin promotion, no auth headers override) — it's written against the
END STATE this task produces (export no longer requires admin). It will
fail for TWO reasons until this task is done: the route still requires
`get_current_admin` (403, not the assertion failing) AND `build_backup`
doesn't take a `user_id` yet. Both are exactly what this task fixes.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_backup.py -v -k test_export_only_includes`
Expected: FAIL (403, since export is still admin-gated at this point).

- [ ] **Step 3: Scope `build_backup`**

Modify `backend/app/services/backup_service.py`. Add to imports:

```python
from app.services.scoped import scoped
from app.services.settings_service import get_or_create_app_settings
```

Replace `build_backup`:

```python
async def build_backup(session: AsyncSession, user_id: int) -> BackupPayload:
    accounts = (await session.execute(scoped(select(Account), Account, user_id))).scalars().all()
    categories = (await session.execute(scoped(select(Category), Category, user_id))).scalars().all()
    tags = (await session.execute(scoped(select(Tag), Tag, user_id))).scalars().all()
    transactions = (
        await session.execute(
            scoped(select(Transaction), Transaction, user_id).options(selectinload(Transaction.tags))
        )
    ).scalars().all()
    # transaction_splits has no user_id column of its own (see
    # models/transaction.py) — scoped via a join to its parent Transaction,
    # same idiom used throughout this series wherever a child table lacks
    # its own user_id (see services/category_rollup.py, reports_service.py).
    transaction_splits = (
        await session.execute(
            select(TransactionSplit)
            .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
            .where(Transaction.user_id == user_id)
        )
    ).scalars().all()
    assets = (await session.execute(scoped(select(Asset), Asset, user_id))).scalars().all()
    valuations = (await session.execute(scoped(select(AssetValuation), AssetValuation, user_id))).scalars().all()
    crypto_portfolios = (
        await session.execute(scoped(select(CryptoPortfolio), CryptoPortfolio, user_id))
    ).scalars().all()
    crypto_holdings = (
        await session.execute(scoped(select(CryptoHolding), CryptoHolding, user_id))
    ).scalars().all()
    crypto_transactions = (
        await session.execute(scoped(select(CryptoTransaction), CryptoTransaction, user_id))
    ).scalars().all()
    budgets = (await session.execute(scoped(select(Budget), Budget, user_id))).scalars().all()
    goals = (await session.execute(scoped(select(Goal), Goal, user_id))).scalars().all()
    # goal_contributions has no user_id column of its own — same
    # join-through-parent idiom as transaction_splits above.
    goal_contributions = (
        await session.execute(
            select(GoalContribution).join(Goal, Goal.id == GoalContribution.goal_id).where(Goal.user_id == user_id)
        )
    ).scalars().all()
    recurring_transactions = (
        await session.execute(scoped(select(RecurringTransaction), RecurringTransaction, user_id))
    ).scalars().all()
    app_settings = await get_or_create_app_settings(session, user_id)

    return BackupPayload(
        aurum_backup_version=BACKUP_FORMAT_VERSION,
        exported_at=datetime.now(timezone.utc),
        app_version=APP_VERSION,
        accounts=[AccountBackup.model_validate(row) for row in accounts],
        categories=[CategoryBackup.model_validate(row) for row in categories],
        tags=[TagBackup.model_validate(row) for row in tags],
        transactions=[
            TransactionBackup.model_validate(row, from_attributes=True).model_copy(
                update={"tag_ids": [tag.id for tag in row.tags]}
            )
            for row in transactions
        ],
        transaction_splits=[TransactionSplitBackup.model_validate(row) for row in transaction_splits],
        assets=[AssetBackup.model_validate(row) for row in assets],
        asset_valuations=[AssetValuationBackup.model_validate(row) for row in valuations],
        crypto_portfolios=[CryptoPortfolioBackup.model_validate(row) for row in crypto_portfolios],
        crypto_holdings=[CryptoHoldingBackup.model_validate(row) for row in crypto_holdings],
        crypto_transactions=[CryptoTransactionBackup.model_validate(row) for row in crypto_transactions],
        budgets=[BudgetBackup.model_validate(row) for row in budgets],
        goals=[GoalBackup.model_validate(row) for row in goals],
        goal_contributions=[GoalContributionBackup.model_validate(row) for row in goal_contributions],
        recurring_transactions=[RecurringTransactionBackup.model_validate(row) for row in recurring_transactions],
        app_settings=AppSettingsBackup.model_validate(app_settings),
    )
```

Note: `get_or_create_app_settings` always returns a real row (creating one
if missing), so the old `AppSettingsBackup.model_validate(app_settings) if
app_settings else AppSettingsBackup(currency="USD")` fallback is no longer
needed — simplified to a plain `model_validate` call.

- [ ] **Step 4: Wire the export route**

Modify `backend/app/api/routes/backup.py` — replace only the import line
and `export_backup`:

```python
from app.api.deps import get_current_admin, get_current_user, get_session
```

```python
@router.get("/export", response_model=BackupPayload)
async def export_backup(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> BackupPayload:
    return await build_backup(session, current_user.id)
```

Leave `import_backup` and the module-level `# SECURITY (stopgap...)`
comment untouched for now — `import_backup` still calls the old 1-arg
`restore_backup(session, payload)` and is still admin-gated; Task 2 fixes
both and rewrites the comment.

- [ ] **Step 5: Remove now-unnecessary admin promotion from export-only tests**

In `backend/tests/test_backup.py`, `test_backup_roundtrip_preserves_subcategories_and_tags`
and `test_backup_roundtrip_preserves_transaction_splits` both call
`/backup/import` too, so LEAVE their `promote_current_user_to_admin` calls
in place for now (Task 2's job). No existing test in this file calls
`/backup/export` alone without also importing, so no removal is needed in
this step beyond what Step 1 already added as a new test.

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_backup.py -v -k test_export_only_includes`
Expected: PASS.

- [ ] **Step 7: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: the two `promote_current_user_to_admin`-calling round-trip tests
in `test_backup.py`, and the three in `test_crypto.py`, will now fail
differently than their `xfail` reason describes — they call
`/backup/import`, which still calls the OLD 1-arg `restore_backup`, but
`export_backup` (called first, inside those same tests, to build the
payload to import) now works correctly. Confirm the failure they hit is
whatever `import_backup`/`restore_backup` produces today (still admin-only,
so these tests' own `promote_current_user_to_admin` call keeps them past
that gate, meaning they should reach `restore_backup` and behave exactly
as before this task — i.e., these 5 `xfail` tests should show the SAME
xfail (not a new, different failure) since `restore_backup` itself is
untouched by this task). Every other test should be unaffected. If any of
the 5 `xfail` tests show a NEW/different error message than before this
task, investigate before proceeding — that would mean this task
accidentally broke something in the read path Task 2 doesn't yet cover.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/backup_service.py backend/app/api/routes/backup.py backend/tests/test_backup.py
git commit -m "Изолировать экспорт бэкапа по пользователю"
```

---

## Task 2: Scope `restore_backup` (import) for per-user + fix the sequence-reset bug + wire the import route

**Files:**
- Modify: `backend/app/services/backup_service.py` (`restore_backup`, `_reset_sequence`)
- Modify: `backend/app/api/routes/backup.py` (rest of the file: `import_backup`, module docstring)

**Interfaces:**
- Produces: `restore_backup(session, payload, user_id) -> None` — gains a
  required `user_id: int` parameter. `_reset_sequence(session, table) ->
  None` — loses its `rows: list` parameter entirely (queries the live
  table instead).

This is the highest-risk task in this plan — read the Architecture section
above again before starting. The core invariant: **after this function
returns, no row belonging to any user other than `user_id` may have been
read, modified, or deleted, and no future ordinary `INSERT` by any user may
collide with an id this function just wrote.**

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_backup.py`:

```python
async def test_import_never_touches_another_users_data(client: AsyncClient, account_id, categories):
    """The single most important property of self-service restore: importing
    a backup must only ever affect the calling user's own rows."""
    from tests.helpers import auth_headers, register_user

    b_tokens = await register_user(client, "backupb2@example.com")
    b_account_resp = await client.post(
        "/accounts", json={"name": "B Wallet", "type": "cash", "currency": "USD"},
        headers=auth_headers(b_tokens["access_token"]),
    )
    b_account_id = b_account_resp.json()["id"]

    payload = (await client.get("/backup/export")).json()
    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    b_accounts = (await client.get("/accounts", headers=auth_headers(b_tokens["access_token"]))).json()
    assert any(a["id"] == b_account_id for a in b_accounts)


async def test_import_does_not_break_sequence_for_other_users(client: AsyncClient, account_id, categories):
    """Regression guard for the sequence-reset bug this task fixes: restoring
    a user's own OLD, low-numbered backup must never roll the shared id
    sequence backward below ids another user's rows already occupy — doing
    so would make a future ordinary INSERT by that other user collide with
    their own existing row."""
    from tests.helpers import auth_headers, register_user

    payload = (await client.get("/backup/export")).json()  # A's own backup, low ids

    b_tokens = await register_user(client, "backupb3@example.com")
    b_headers = auth_headers(b_tokens["access_token"])
    # Push the shared accounts-table sequence well past A's own ids.
    for i in range(5):
        resp = await client.post(
            "/accounts", json={"name": f"B Account {i}", "type": "cash", "currency": "USD"}, headers=b_headers
        )
        assert resp.status_code == 201

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    # If the sequence were wrongly rolled back to A's own (lower) backup
    # max, this next INSERT would collide with one of B's 5 accounts above
    # and 500 instead of 201.
    new_b_account = await client.post(
        "/accounts", json={"name": "B Account After Restore", "type": "cash", "currency": "USD"}, headers=b_headers
    )
    assert new_b_account.status_code == 201
    b_accounts = (await client.get("/accounts", headers=b_headers)).json()
    assert len({a["id"] for a in b_accounts}) == len(b_accounts)  # no duplicate ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_backup.py -v -k "test_import_never_touches or test_import_does_not_break_sequence"`
Expected: FAIL — both currently 403 (import still admin-gated, no auth
header override in these tests since the whole point is testing the
NEW, non-admin-gated behavior).

- [ ] **Step 3: Fix `_reset_sequence`**

Modify `backend/app/services/backup_service.py`. Replace `_reset_sequence`:

```python
async def _reset_sequence(session: AsyncSession, table: str) -> None:
    """Bulk-inserting rows with explicit ids doesn't advance the table's
    identity sequence, so a future auto-generated id could collide with a
    row this restore (or any other user's normal usage) already holds.
    Bumps the sequence to the table's actual LIVE max id — never to just
    this restore's own payload's max — because other users' rows may
    already occupy higher ids than anything in this one user's backup, and
    lowering the sequence below those would make their very next ordinary
    INSERT collide with their own existing data. `MAX(id)` here naturally
    reflects both those other rows AND whatever this restore just inserted,
    so this is correct regardless of how the two interleave. `table` is
    always one of our hardcoded table names, never user input, so it's
    safe to interpolate directly into the SQL."""
    await session.execute(
        text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1))")
    )
```

- [ ] **Step 4: Scope `restore_backup`**

Replace `restore_backup`:

```python
async def restore_backup(session: AsyncSession, payload: BackupPayload, user_id: int) -> None:
    """Restore this user's own data from a JSON snapshot — see module
    docstring for the snapshot-restore/transaction semantics.

    Deletes and replaces ONLY the calling user's own rows, then rebuilds
    them from `payload`, stamping every restored row with this same
    user_id regardless of anything (or nothing) the payload itself
    implies about ownership — the payload schema carries no user_id field
    at all. Another user's data is never read, modified, or deleted by
    this function: a huge, stale, or malicious payload can corrupt or wipe
    only the calling user's own account, never anyone else's.
    """
    if payload.aurum_backup_version != BACKUP_FORMAT_VERSION:
        raise HTTPException(
            400,
            f"Unsupported backup version {payload.aurum_backup_version} "
            f"(this Aurum version supports {BACKUP_FORMAT_VERSION})",
        )

    _validate_references(payload)

    try:
        # Children before parents, respecting FK ON DELETE constraints
        # (CryptoHolding -> CryptoPortfolio is ON DELETE RESTRICT, so
        # holdings must be gone before their portfolio). TransactionSplit
        # and GoalContribution have no user_id column of their own (see
        # models/transaction.py, models/goal.py) — deleting their scoped
        # parent (Transaction, Goal) cascades them automatically via each
        # child's ON DELETE CASCADE, so no separate statement is needed or
        # even possible to scope directly by user_id for those two.
        await session.execute(delete(AssetValuation).where(AssetValuation.user_id == user_id))
        await session.execute(delete(CryptoTransaction).where(CryptoTransaction.user_id == user_id))
        await session.execute(delete(CryptoHolding).where(CryptoHolding.user_id == user_id))
        await session.execute(delete(CryptoPortfolio).where(CryptoPortfolio.user_id == user_id))
        await session.execute(delete(Budget).where(Budget.user_id == user_id))
        await session.execute(delete(Goal).where(Goal.user_id == user_id))
        await session.execute(delete(RecurringTransaction).where(RecurringTransaction.user_id == user_id))
        await session.execute(delete(Transaction).where(Transaction.user_id == user_id))
        await session.execute(delete(Tag).where(Tag.user_id == user_id))
        await session.execute(delete(Asset).where(Asset.user_id == user_id))
        await session.execute(delete(Category).where(Category.user_id == user_id))
        await session.execute(delete(Account).where(Account.user_id == user_id))

        # Parents before children. Categories are additionally self-referential
        # (parent_id points at another row in the same table) — sort
        # top-level categories first so a subcategory's FK is never inserted
        # ahead of the row it points to.
        categories_in_order = sorted(payload.categories, key=lambda row: row.parent_id is not None)

        session.add_all(Account(**row.model_dump(), user_id=user_id) for row in payload.accounts)
        session.add_all(Category(**row.model_dump(), user_id=user_id) for row in categories_in_order)
        session.add_all(Asset(**row.model_dump(), user_id=user_id) for row in payload.assets)

        # Tags and transactions are kept in id-keyed dicts (rather than a
        # plain add_all) — transaction.tags is a relationship, not a column
        # in model_dump(), so it has to be wired up from live ORM objects
        # once everything is flushed and has real identities.
        tags_by_id = {row.id: Tag(**row.model_dump(), user_id=user_id) for row in payload.tags}
        session.add_all(tags_by_id.values())
        # tags=[] at construction keeps the collection "loaded" on the
        # transient object — reassigning it after flush (below) would
        # otherwise trigger an implicit lazy-load, which async SQLAlchemy
        # can't do outside an explicit await (MissingGreenlet).
        transactions_by_id = {
            row.id: Transaction(**row.model_dump(exclude={"tag_ids"}), tags=[], user_id=user_id)
            for row in payload.transactions
        }
        session.add_all(transactions_by_id.values())
        session.add_all(TransactionSplit(**row.model_dump()) for row in payload.transaction_splits)

        session.add_all(AssetValuation(**row.model_dump(), user_id=user_id) for row in payload.asset_valuations)

        session.add_all(CryptoPortfolio(**row.model_dump(), user_id=user_id) for row in payload.crypto_portfolios)
        # A pre-portfolios backup has no crypto_portfolios and every holding's
        # portfolio_id is None — give those holdings a freshly created
        # fallback portfolio instead of leaving the NOT NULL column unset.
        # Wired up via the `portfolio` relationship (not a raw portfolio_id
        # int) because the fallback row has no id yet — same "assign the
        # relationship, not the id column, before flush" reasoning as
        # transactions_by_id/tags_by_id above.
        fallback_portfolio: CryptoPortfolio | None = None
        if any(row.portfolio_id is None for row in payload.crypto_holdings):
            fallback_portfolio = CryptoPortfolio(name="Main Portfolio", color="#2a78d6", user_id=user_id)
            session.add(fallback_portfolio)

        crypto_holdings = []
        for row in payload.crypto_holdings:
            holding = CryptoHolding(**row.model_dump(exclude={"portfolio_id"}), user_id=user_id)
            if row.portfolio_id is not None:
                holding.portfolio_id = row.portfolio_id
            else:
                holding.portfolio = fallback_portfolio
            crypto_holdings.append(holding)
        session.add_all(crypto_holdings)

        session.add_all(CryptoTransaction(**row.model_dump(), user_id=user_id) for row in payload.crypto_transactions)
        session.add_all(Budget(**row.model_dump(), user_id=user_id) for row in payload.budgets)
        session.add_all(Goal(**row.model_dump(), user_id=user_id) for row in payload.goals)
        session.add_all(GoalContribution(**row.model_dump()) for row in payload.goal_contributions)
        session.add_all(
            RecurringTransaction(**row.model_dump(), user_id=user_id) for row in payload.recurring_transactions
        )
        await session.flush()

        for row in payload.transactions:
            if row.tag_ids:
                transactions_by_id[row.id].tags = [tags_by_id[tag_id] for tag_id in row.tag_ids]
        if any(row.tag_ids for row in payload.transactions):
            await session.flush()

        await _reset_sequence(session, "accounts")
        await _reset_sequence(session, "categories")
        await _reset_sequence(session, "tags")
        await _reset_sequence(session, "assets")
        await _reset_sequence(session, "transactions")
        await _reset_sequence(session, "transaction_splits")
        await _reset_sequence(session, "asset_valuations")
        await _reset_sequence(session, "crypto_portfolios")
        await _reset_sequence(session, "crypto_transactions")
        await _reset_sequence(session, "budgets")
        await _reset_sequence(session, "goals")
        await _reset_sequence(session, "goal_contributions")
        await _reset_sequence(session, "recurring_transactions")

        settings_row = await get_or_create_app_settings(session, user_id)
        for field, value in payload.app_settings.model_dump().items():
            setattr(settings_row, field, value)

        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        raise HTTPException(400, f"Restore failed, no changes were made: {exc}") from exc
```

- [ ] **Step 5: Wire the import route and rewrite the module docstring**

Modify `backend/app/api/routes/backup.py` — replace the whole file:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.backup import BackupPayload
from app.services.backup_service import build_backup, restore_backup

router = APIRouter(prefix="/backup", tags=["backup"])


@router.get("/export", response_model=BackupPayload)
async def export_backup(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> BackupPayload:
    return await build_backup(session, current_user.id)


@router.post("/import")
async def import_backup(
    payload: BackupPayload,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    await restore_backup(session, payload, current_user.id)
    return {"status": "ok"}
```

(`get_current_admin` is no longer imported here — both endpoints now only
require an authenticated user, same as every other feature route.)

- [ ] **Step 6: Remove now-unnecessary admin promotion from every backup test**

In `backend/tests/test_backup.py`: remove the `promote_current_user_to_admin`
call and its `test_sessionmaker` fixture parameter from all 3 functions —
`test_backup_roundtrip_preserves_subcategories_and_tags`,
`test_backup_import_rejects_transaction_with_unknown_tag_id`, and
`test_backup_roundtrip_preserves_transaction_splits` — confirmed by reading
the file directly that both are used ONLY in these 3 places. Also remove
`promote_current_user_to_admin` from the `from tests.helpers import ...`
line at the top of the file (confirmed nothing else in the file references
it).

In `backend/tests/test_crypto.py`: remove the `promote_current_user_to_admin`
call (and its inline `# /backup/* is admin-gated (see backup.py)` comment,
now inaccurate) from `test_backup_roundtrip_preserves_holding_and_transaction_log`,
`test_backup_roundtrip_preserves_portfolio_assignment`, and
`test_restoring_a_pre_portfolios_backup_falls_back_to_a_default_portfolio`.
Confirmed by reading the file directly: `promote_current_user_to_admin` and
`test_sessionmaker` are used ONLY inside these 3 functions in this file —
after removing the call, also remove the now-unused `test_sessionmaker`
parameter from each of these 3 functions' signatures, and remove
`promote_current_user_to_admin` from the `from tests.helpers import ...`
line at the top of the file (confirmed nothing else in the file references
it).

- [ ] **Step 7: Remove the now-passing `xfail` markers**

In `backend/tests/test_backup.py`: remove the entire
`@pytest.mark.xfail(reason="backup_service.py doesn't stamp user_id on
restored rows yet — deferred to the Part 3 multi-tenant plan", strict=True)`
decorator (all 4 lines including the blank line after it, if any) from both
`test_backup_roundtrip_preserves_subcategories_and_tags` and
`test_backup_roundtrip_preserves_transaction_splits`. Confirmed by reading
the file directly: these are the ONLY 2 uses of `pytest.` anywhere in this
file — after removing both, also remove the now-unused `import pytest`
line. Re-run `grep -n "pytest\." tests/test_backup.py` yourself after
editing to confirm it returns nothing before removing the import, in case
this plan's reading of the file is stale by the time you implement it.

In `backend/tests/test_crypto.py`: remove the same decorator from all 3
tests named in Step 6. Confirmed by reading the file directly: `pytest.` is
used ONLY in these 3 `@pytest.mark.xfail(...)` decorators anywhere in this
file (no `pytest.raises`, `pytest.fixture`, `pytest.mark.parametrize`, etc.)
— after removing all 3, also remove the now-unused `import pytest` line
from the top of the file. Re-run `grep -n "pytest\." tests/test_crypto.py`
yourself after editing to confirm it returns nothing before removing the
import, in case this plan's reading of the file is stale by the time you
implement it.

- [ ] **Step 8: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_backup.py tests/test_crypto.py -v`
Expected: PASS — every test in both files, including the 5 formerly-`xfail`
tests now passing for real (not `xfail`), and the 2 new isolation/collision
tests from Step 1.

- [ ] **Step 9: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS, with exactly 0 `xfail` remaining anywhere in the suite
(the 5 this plan fixes were the only ones in the whole codebase — confirm
with `grep -rn "pytest.mark.xfail" backend/tests/` returning nothing).

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/backup_service.py backend/app/api/routes/backup.py backend/tests/test_backup.py backend/tests/test_crypto.py
git commit -m "Изолировать восстановление бэкапа по пользователю и исправить сброс sequence"
```

---

## Plan Self-Review Notes

- **Spec coverage:** Implements the backup half of "Part 3" explicitly
  named in Part 2B's and Part 3A's own "Next Plan" sections, per the
  user's explicit direction to make backup self-service (not merely
  admin-scoped-by-user_id) — a genuine product decision confirmed before
  writing this plan, not assumed.
- **Type/interface consistency:** `build_backup`'s and `restore_backup`'s
  new `user_id: int` parameter positions match between their definitions
  (Task 1/Task 2) and their route call sites (`current_user.id`, same
  tasks). `_reset_sequence`'s signature change (losing its `rows`
  parameter) is applied consistently at all 13 call sites within
  `restore_backup` in the same task that changes its definition — no
  caller elsewhere in the codebase (`grep -rn "_reset_sequence"
  backend/app/` confirms it is only ever called from within
  `restore_backup` itself).
- **No placeholders:** every step contains complete, real code, including
  the full rewritten bodies of `build_backup`, `restore_backup`, and
  `_reset_sequence` — nothing is left as "similar to above" or elided.
- **The sequence-bump bug**, the single riskiest correctness issue in this
  plan, has a dedicated regression test (Task 2 Step 1's
  `test_import_does_not_break_sequence_for_other_users`) that concretely
  reproduces the exact failure mode the old code would have hit (another
  user's existing row colliding with a freshly-`nextval()`'d id after a
  low-numbered restore) rather than just asserting the fix's mechanism in
  the abstract.

---

## Next Plan

**Part 3C (final cutover):** the final migration flipping every `user_id`
column added across Parts 1, 2A, 2B, and 3A to `NOT NULL` (now safe once
backup/restore, the last unscoped write path, is fixed by this plan);
retiring `AURUM_BASIC_AUTH_USER`/`PASSWORD` and nginx's `auth_basic` (see
`docker-compose.yml`, `frontend/nginx.conf`,
`frontend/docker-entrypoint.d/20-basic-auth.sh`,
`frontend/src/components/auth/LoginGate.tsx`, `frontend/src/lib/auth.ts`) —
now safely supersedable since every backend route enforces real per-user
JWT auth and no route depends on Basic Auth for protection. After that,
frontend login/registration screens and the originally-requested Android
(Capacitor) app become unblocked.
