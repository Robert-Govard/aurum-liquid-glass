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
