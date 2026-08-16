from pydantic import BaseModel, Field


class AppSettingsRead(BaseModel):
    currency: str
    negative_cash_flow_threshold_months: int
    net_worth_decline_threshold_months: int
    risky_allocation_threshold_percent: int


class AppSettingsUpdate(BaseModel):
    """All fields optional — the route applies a partial update
    (`exclude_unset`), same as CategoryUpdate, so a single-field PATCH from
    e.g. CurrencyCard doesn't need to resend the alert thresholds."""

    # ISO 4217 code, e.g. "USD"/"UAH"/"EUR" — the frontend only ever sends
    # values from its curated currency list, but validate the shape anyway
    # since Intl.NumberFormat would otherwise silently accept garbage.
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    # Consecutive complete months before the corresponding alert fires.
    # Capped at 24 to match insights_service.py's MAX_LOOKBACK_MONTHS.
    negative_cash_flow_threshold_months: int | None = Field(default=None, ge=1, le=24)
    net_worth_decline_threshold_months: int | None = Field(default=None, ge=1, le=24)
    # Max % of capital allowed in medium/high risk tiers (the 80/20 rule's
    # "20% at most exposed" half) before risky_allocation_exceeded fires.
    risky_allocation_threshold_percent: int | None = Field(default=None, ge=1, le=100)
