from typing import Literal

from pydantic import BaseModel


class AdviceItem(BaseModel):
    key: str
    tone: Literal["positive", "neutral", "warning"]
    # Frontend-translated by key — same key+params pattern as FinancialAlert,
    # extended to allow string params (category names) alongside numbers.
    params: dict[str, str | int | float]


class AdviceResponse(BaseModel):
    items: list[AdviceItem]
