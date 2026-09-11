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
