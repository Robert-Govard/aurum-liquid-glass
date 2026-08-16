"""Long-range spending reports — the analysis the month-scoped Dashboard
breakdown can't answer on its own: "how much did I spend on X this month,
and how much in total over N years" (single-category detail), and "which
categories cost the most over this whole period" (ranking, across all
categories of one kind at once, not just the current month).
"""
from datetime import date as date_
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.enums import CategoryKind, TransactionType
from app.models.transaction import Transaction
from app.schemas.reports import (
    CategoryRankingItem,
    CategoryRankingReport,
    CategorySpendingPoint,
    CategorySpendingReport,
)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


async def get_category_spending_report(
    session: AsyncSession, category_id: int, start_date: date_ | None, end_date: date_ | None
) -> CategorySpendingReport:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    bounds_stmt = select(func.min(Transaction.date), func.max(Transaction.date)).where(
        Transaction.category_id == category_id
    )
    if start_date:
        bounds_stmt = bounds_stmt.where(Transaction.date >= start_date)
    if end_date:
        bounds_stmt = bounds_stmt.where(Transaction.date <= end_date)
    min_date, max_date = (await session.execute(bounds_stmt)).one()

    effective_start = start_date or min_date
    effective_end = end_date or max_date

    empty = CategorySpendingReport(
        category_id=category.id,
        category_name=category.name,
        category_color=category.color,
        category_icon=category.icon,
        start_date=effective_start,
        end_date=effective_end,
        total_amount=Decimal("0"),
        transaction_count=0,
        average_per_month=Decimal("0"),
        series=[],
    )
    if effective_start is None or effective_end is None:
        return empty

    rows_stmt = (
        select(
            extract("year", Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
            func.sum(Transaction.amount).label("amount"),
            func.count(Transaction.id).label("cnt"),
        )
        .where(
            Transaction.category_id == category_id,
            Transaction.date >= effective_start,
            Transaction.date <= effective_end,
        )
        .group_by("year", "month")
    )
    rows = (await session.execute(rows_stmt)).all()
    by_month: dict[tuple[int, int], Decimal] = {(int(row.year), int(row.month)): row.amount for row in rows}
    total_amount = sum((row.amount for row in rows), Decimal("0"))
    total_count = sum(row.cnt for row in rows)

    series: list[CategorySpendingPoint] = []
    year, month = effective_start.year, effective_start.month
    while (year, month) <= (effective_end.year, effective_end.month):
        series.append(CategorySpendingPoint(year=year, month=month, amount=by_month.get((year, month), Decimal("0"))))
        year, month = _next_month(year, month)

    months_count = len(series)
    average_per_month = (total_amount / months_count).quantize(Decimal("0.01")) if months_count else Decimal("0")

    return CategorySpendingReport(
        category_id=category.id,
        category_name=category.name,
        category_color=category.color,
        category_icon=category.icon,
        start_date=effective_start,
        end_date=effective_end,
        total_amount=total_amount,
        transaction_count=total_count,
        average_per_month=average_per_month,
        series=series,
    )


_KIND_TO_TRANSACTION_TYPE = {
    CategoryKind.EXPENSE: TransactionType.EXPENSE,
    CategoryKind.INCOME: TransactionType.INCOME,
}


async def get_category_ranking_report(
    session: AsyncSession, kind: CategoryKind, start_date: date_ | None, end_date: date_ | None
) -> CategoryRankingReport:
    """All categories of one kind, ranked by total spent/earned over an
    arbitrary period — "which category costs the most" across the whole
    range, unlike the month-scoped Dashboard breakdown or the
    single-category detail above."""
    stmt = (
        select(
            Category.id,
            Category.name,
            Category.color,
            Category.icon,
            func.sum(Transaction.amount).label("amount"),
            func.count(Transaction.id).label("cnt"),
        )
        .join(Category, Category.id == Transaction.category_id)
        .where(Category.kind == kind, Transaction.type == _KIND_TO_TRANSACTION_TYPE[kind])
    )
    if start_date:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date:
        stmt = stmt.where(Transaction.date <= end_date)
    stmt = stmt.group_by(Category.id, Category.name, Category.color, Category.icon, Category.sort_order)
    stmt = stmt.order_by(func.sum(Transaction.amount).desc(), Category.sort_order)

    rows = (await session.execute(stmt)).all()
    total_amount = sum((row.amount for row in rows), Decimal("0"))

    def _percent(amount: Decimal) -> float:
        return float(amount / total_amount * 100) if total_amount else 0.0

    items = [
        CategoryRankingItem(
            category_id=cat_id,
            name=name,
            color=color,
            icon=icon,
            amount=amount,
            percent=_percent(amount),
            transaction_count=cnt,
        )
        for cat_id, name, color, icon, amount, cnt in rows
    ]

    return CategoryRankingReport(
        start_date=start_date, end_date=end_date, total_amount=total_amount, items=items
    )
