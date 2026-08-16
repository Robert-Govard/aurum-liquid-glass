from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel


class CategorySpendingPoint(BaseModel):
    year: int
    month: int
    amount: Decimal


class CategorySpendingReport(BaseModel):
    category_id: int
    category_name: str
    category_color: str
    category_icon: str | None
    start_date: date_ | None
    end_date: date_ | None
    total_amount: Decimal
    transaction_count: int
    average_per_month: Decimal
    series: list[CategorySpendingPoint]


class CategoryRankingItem(BaseModel):
    category_id: int
    name: str
    color: str
    icon: str | None
    amount: Decimal
    percent: float
    transaction_count: int


class CategoryRankingReport(BaseModel):
    start_date: date_ | None
    end_date: date_ | None
    total_amount: Decimal
    items: list[CategoryRankingItem]
