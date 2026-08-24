"""Aggregation logic behind the Overview dashboard."""
import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.schemas.dashboard import CategoryBreakdownItem, DashboardSummary

# Categorical slots are capped at 8 (dataviz skill: a 9th series folds into "Other",
# never a generated hue) — this is also the exact size of the default category set.
MAX_CHART_SLICES = 8
OTHER_SLICE_COLOR = "#898781"  # muted ink, reserved for the non-categorical rollup


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


async def get_dashboard_summary(session: AsyncSession, year: int, month: int) -> DashboardSummary:
    start, end = _month_bounds(year, month)

    totals_stmt = (
        select(Transaction.type, func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.date >= start, Transaction.date <= end)
        .group_by(Transaction.type)
    )
    totals_result = await session.execute(totals_stmt)
    totals: dict[TransactionType, Decimal] = {row[0]: row[1] for row in totals_result.all()}

    real_income = totals.get(TransactionType.INCOME, Decimal("0"))
    spent = totals.get(TransactionType.EXPENSE, Decimal("0"))
    transferred_out = totals.get(TransactionType.TRANSFER, Decimal("0"))

    # A subcategory's spending rolls up into its parent's slice — Parent is a
    # self-join to resolve each transaction's *top-level* category, falling
    # back to the transaction's own category when it has no parent.
    Parent = aliased(Category)
    effective_id = func.coalesce(Category.parent_id, Category.id)
    effective_name = func.coalesce(Parent.name, Category.name)
    effective_color = func.coalesce(Parent.color, Category.color)
    effective_icon = func.coalesce(Parent.icon, Category.icon)
    effective_sort = func.coalesce(Parent.sort_order, Category.sort_order)

    breakdown_stmt = (
        select(
            effective_id.label("category_id"),
            effective_name.label("name"),
            effective_color.label("color"),
            effective_icon.label("icon"),
            func.coalesce(func.sum(Transaction.amount), 0).label("amount"),
        )
        .join(Category, Category.id == Transaction.category_id)
        .outerjoin(Parent, Parent.id == Category.parent_id)
        .where(
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.type == TransactionType.EXPENSE,
        )
        .group_by(effective_id, effective_name, effective_color, effective_icon, effective_sort)
        .order_by(func.sum(Transaction.amount).desc(), effective_sort)
    )
    breakdown_result = await session.execute(breakdown_stmt)
    rows = breakdown_result.all()

    top_rows, rest_rows = rows[:MAX_CHART_SLICES], rows[MAX_CHART_SLICES:]

    def _percent(amount: Decimal) -> float:
        return float(amount / spent * 100) if spent else 0.0

    spending_by_category = [
        CategoryBreakdownItem(
            category_id=cat_id, name=name, color=color, icon=icon, amount=amount, percent=_percent(amount)
        )
        for cat_id, name, color, icon, amount in top_rows
    ]

    if rest_rows:
        other_amount = sum((row.amount for row in rest_rows), Decimal("0"))
        spending_by_category.append(
            CategoryBreakdownItem(
                category_id=None, name="Other", color=OTHER_SLICE_COLOR, icon="more-horizontal",
                amount=other_amount, percent=_percent(other_amount),
            )
        )

    return DashboardSummary(
        year=year,
        month=month,
        real_income=real_income,
        spent=spent,
        net=real_income - spent,
        transferred_out=transferred_out,
        spending_by_category=spending_by_category,
    )
