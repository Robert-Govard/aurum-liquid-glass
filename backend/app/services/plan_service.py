"""The single place that answers "is this user Premium" and "how many
of X do they already have." Every Premium-gated route imports from here
instead of re-deriving the same checks — see the spec's Global
Constraints for the exact limits and which features are fully gated."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.asset import Asset
from app.models.category import Category
from app.models.recurring import RecurringTransaction
from app.models.user import User
from app.services.scoped import get_owned_or_404, scoped

FREE_ACCOUNT_LIMIT = 3
FREE_ASSET_LIMIT = 2
FREE_CUSTOM_CATEGORY_LIMIT = 5
FREE_RECURRING_LIMIT = 5

# Known v1 limitation, accepted deliberately (see the final review of the
# premium-subscription plan): these four limits are enforced only at the
# four creation routes (and the two reactivation paths in routes/accounts.py
# and routes/recurring.py) — POST /backup/import can still let a Free user
# exceed them by restoring a crafted or old, larger backup. Not fixed for
# v1: restore is destructive to the importer's own data (nobody stumbles
# into this by accident), and this instance is single-operator with every
# user known personally, so an anomaly is visible in the admin panel's own
# per-user counts. If this class of gap becomes worth closing later, do it
# once via a shared helper called from creation, from reactivation, AND
# from backup_service.restore_backup — not as three more bespoke checks.


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


async def enforce_account_reactivation_limit(session: AsyncSession, user: User, account_id: int) -> None:
    """Called from the account update route when a payload tries to
    un-archive an account (is_archived: true -> false) — count_accounts()
    only counts non-archived rows, so without this check a Free user
    could archive-create-unarchive their way past FREE_ACCOUNT_LIMIT
    through completely normal UI clicks. Fetches the account's CURRENT
    state first so a no-op re-save of an already-unarchived account (or
    any update that doesn't touch is_archived) is never blocked."""
    if is_premium(user):
        return
    account = await get_owned_or_404(session, Account, account_id, user.id, detail="Account not found")
    if account.is_archived and await count_accounts(session, user.id) >= FREE_ACCOUNT_LIMIT:
        raise HTTPException(status_code=402, detail="Free plan account limit reached")


async def enforce_recurring_reactivation_limit(session: AsyncSession, user: User, recurring_id: int) -> None:
    """Same idea as enforce_account_reactivation_limit, for recurring
    transactions' is_active toggle instead of accounts' is_archived."""
    if is_premium(user):
        return
    recurring = await get_owned_or_404(
        session, RecurringTransaction, recurring_id, user.id, detail="Recurring transaction not found"
    )
    if not recurring.is_active and await count_active_recurring(session, user.id) >= FREE_RECURRING_LIMIT:
        raise HTTPException(status_code=402, detail="Free plan recurring transaction limit reached")
