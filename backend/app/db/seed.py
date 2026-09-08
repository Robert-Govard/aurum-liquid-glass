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
