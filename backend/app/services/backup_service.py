"""Self-service, per-user JSON backup & restore.

Exports every row belonging to the CALLING user only (accounts, categories,
transactions, assets, asset valuations, and the rest of that user's own
data) as one portable JSON document they can download from the browser and
re-upload later. Restore fully REPLACES that same user's own existing
data — it's a snapshot restore, not a merge — but never touches any other
user's rows: every query and delete is scoped by user_id, so a user's own
backup/restore cycle can never read, corrupt, or wipe another user's
account. The whole restore runs in one DB transaction: a corrupt or
incompatible file is rejected (referential checks run first, before any row
is touched), and any failure during the swap rolls the database back to
exactly where it was, so a bad file never leaves the app half-restored.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import APP_VERSION
from app.models.account import Account
from app.models.asset import Asset, AssetValuation
from app.models.budget import Budget
from app.models.category import Category
from app.models.crypto import CryptoHolding, CryptoPortfolio, CryptoTransaction
from app.models.goal import Goal, GoalContribution
from app.models.recurring import RecurringTransaction
from app.models.tag import Tag
from app.models.transaction import Transaction, TransactionSplit
from app.schemas.backup import (
    AccountBackup,
    AppSettingsBackup,
    AssetBackup,
    AssetValuationBackup,
    BackupPayload,
    BudgetBackup,
    CategoryBackup,
    CryptoHoldingBackup,
    CryptoPortfolioBackup,
    CryptoTransactionBackup,
    GoalBackup,
    GoalContributionBackup,
    RecurringTransactionBackup,
    TagBackup,
    TransactionBackup,
    TransactionSplitBackup,
)
from app.services.scoped import scoped
from app.services.settings_service import get_or_create_app_settings

BACKUP_FORMAT_VERSION = 1


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


def _validate_references(payload: BackupPayload) -> None:
    account_ids = {row.id for row in payload.accounts}
    category_ids = {row.id for row in payload.categories}
    asset_ids = {row.id for row in payload.assets}
    tag_ids = {row.id for row in payload.tags}

    for c in payload.categories:
        if c.parent_id is not None and c.parent_id not in category_ids:
            raise HTTPException(400, f"Category {c.id} references unknown parent_id {c.parent_id}")

    for t in payload.transactions:
        if t.account_id not in account_ids:
            raise HTTPException(400, f"Transaction {t.id} references unknown account_id {t.account_id}")
        if t.transfer_account_id is not None and t.transfer_account_id not in account_ids:
            raise HTTPException(
                400, f"Transaction {t.id} references unknown transfer_account_id {t.transfer_account_id}"
            )
        if t.category_id is not None and t.category_id not in category_ids:
            raise HTTPException(400, f"Transaction {t.id} references unknown category_id {t.category_id}")
        for tag_id in t.tag_ids:
            if tag_id not in tag_ids:
                raise HTTPException(400, f"Transaction {t.id} references unknown tag_id {tag_id}")

    transaction_ids = {row.id for row in payload.transactions}
    for s in payload.transaction_splits:
        if s.transaction_id not in transaction_ids:
            raise HTTPException(400, f"Transaction split {s.id} references unknown transaction_id {s.transaction_id}")
        if s.category_id is not None and s.category_id not in category_ids:
            raise HTTPException(400, f"Transaction split {s.id} references unknown category_id {s.category_id}")

    for v in payload.asset_valuations:
        if v.asset_id not in asset_ids:
            raise HTTPException(400, f"Asset valuation {v.id} references unknown asset_id {v.asset_id}")

    crypto_portfolio_ids = {p.id for p in payload.crypto_portfolios}
    crypto_holding_asset_ids = {h.asset_id for h in payload.crypto_holdings}
    for h in payload.crypto_holdings:
        if h.asset_id not in asset_ids:
            raise HTTPException(400, f"Crypto holding {h.asset_id} references unknown asset_id {h.asset_id}")
        # portfolio_id is allowed to be None (a pre-portfolios backup) — that
        # case is resolved to an auto-created fallback portfolio at restore
        # time, not validated here.
        if h.portfolio_id is not None and h.portfolio_id not in crypto_portfolio_ids:
            raise HTTPException(
                400, f"Crypto holding {h.asset_id} references unknown portfolio_id {h.portfolio_id}"
            )

    for tx in payload.crypto_transactions:
        if tx.asset_id not in crypto_holding_asset_ids:
            raise HTTPException(400, f"Crypto transaction {tx.id} references unknown asset_id {tx.asset_id}")

    for b in payload.budgets:
        if b.category_id not in category_ids:
            raise HTTPException(400, f"Budget {b.id} references unknown category_id {b.category_id}")

    goal_ids = {row.id for row in payload.goals}
    for c in payload.goal_contributions:
        if c.goal_id not in goal_ids:
            raise HTTPException(400, f"Goal contribution {c.id} references unknown goal_id {c.goal_id}")

    for r in payload.recurring_transactions:
        if r.account_id not in account_ids:
            raise HTTPException(400, f"Recurring transaction {r.id} references unknown account_id {r.account_id}")
        if r.transfer_account_id is not None and r.transfer_account_id not in account_ids:
            raise HTTPException(
                400,
                f"Recurring transaction {r.id} references unknown transfer_account_id {r.transfer_account_id}",
            )
        if r.category_id is not None and r.category_id not in category_ids:
            raise HTTPException(400, f"Recurring transaction {r.id} references unknown category_id {r.category_id}")


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
    so this is correct regardless of how the two interleave.

    `MAX(id)` alone is still not enough, though: it only sees COMMITTED
    rows. If another user's normal INSERT has already called `nextval()`
    (reserving id N) but that transaction hasn't committed yet while this
    restore runs concurrently, `MAX(id)` can't see the reserved-but-
    uncommitted N, so `setval` could set the sequence below N — and once
    that other transaction commits, a THIRD insert (from anyone) could then
    collide with it. `pg_sequence_last_value` closes this gap: it reflects
    the sequence's own internal counter, i.e. every `nextval()` call ever
    made against it, committed or not, so it can never be fooled by an
    in-flight transaction. Taking `GREATEST` of the two makes the sequence
    monotonic no matter which source currently leads. `table` is always one
    of our hardcoded table names, never user input, so it's safe to
    interpolate directly into the SQL."""
    await session.execute(
        text(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            "GREATEST("
            f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
            f"COALESCE(pg_sequence_last_value(pg_get_serial_sequence('{table}', 'id')), 1)"
            "))"
        )
    )


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
        # No special-casing is needed here to make the fallback portfolio's
        # id visible to `_reset_sequence("crypto_portfolios")` below: once
        # this row is flushed it has a real id like any other, so it's
        # already reflected in the table's live MAX(id) the same as every
        # payload portfolio — the live `_reset_sequence` call covers both
        # without this block needing to know about sequences at all.
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

        # app_settings is a per-user row, looked up (or created if this is
        # the user's very first restore) via get_or_create_app_settings and
        # then updated in place field-by-field below — never deleted and
        # recreated like the tables above. So unlike everything else in this
        # function, it needs no delete/reinsert and no _reset_sequence call:
        # its own identity/sequence is simply never touched by this restore.
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
