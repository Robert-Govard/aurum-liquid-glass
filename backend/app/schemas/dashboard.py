from decimal import Decimal

from pydantic import BaseModel


class CategoryBreakdownItem(BaseModel):
    category_id: int | None
    name: str
    color: str
    icon: str | None
    amount: Decimal
    percent: float


class DashboardSummary(BaseModel):
    year: int
    month: int
    real_income: Decimal
    spent: Decimal
    net: Decimal
    transferred_out: Decimal
    spending_by_category: list[CategoryBreakdownItem]
