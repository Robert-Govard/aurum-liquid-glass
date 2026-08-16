from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, Field


class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    target_amount: Decimal = Field(gt=0)
    target_date: date_ | None = None


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    target_amount: Decimal | None = Field(default=None, gt=0)
    target_date: date_ | None = None


class GoalContributionCreate(BaseModel):
    # Negative allowed — a withdrawal from the goal is still a contribution
    # to its running total, just in the other direction. Zero is pointless.
    amount: Decimal = Field(ne=0)
    date: date_
    note: str | None = Field(default=None, max_length=200)


class GoalRead(BaseModel):
    id: int
    name: str
    target_amount: Decimal
    target_date: date_ | None
    current_amount: Decimal
    remaining: Decimal
    percent: float
    is_reached: bool
