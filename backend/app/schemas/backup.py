"""Shape of a full-database backup file (see services/backup_service.py)."""
from datetime import date as date_
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AccountType,
    AssetClass,
    CapitalRole,
    CategoryKind,
    RecurringFrequency,
    RiskLevel,
    TransactionType,
)


class AccountBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: AccountType
    currency: str
    color: str | None
    is_archived: bool


class CategoryBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: CategoryKind
    icon: str | None
    color: str
    sort_order: int
    is_default: bool


class TransactionBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    category_id: int | None
    transfer_account_id: int | None
    type: TransactionType
    amount: Decimal
    description: str
    merchant: str | None
    notes: str | None
    date: date_


class AssetBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    asset_class: AssetClass
    currency: str
    notes: str | None
    # Defaulted so a backup exported before capital_role/monthly_cash_flow
    # existed still imports cleanly under the same format version.
    capital_role: CapitalRole = CapitalRole.NEUTRAL
    monthly_cash_flow: Decimal | None = None
    # Defaulted so a backup exported before risk_level existed still
    # imports cleanly under the same format version.
    risk_level: RiskLevel = RiskLevel.MEDIUM


class AssetValuationBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    value: Decimal
    as_of_date: date_


class BudgetBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    monthly_limit: Decimal


class GoalBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_amount: Decimal
    target_date: date_ | None


class GoalContributionBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goal_id: int
    amount: Decimal
    date: date_
    note: str | None


class RecurringTransactionBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    category_id: int | None
    transfer_account_id: int | None
    type: TransactionType
    amount: Decimal
    description: str
    merchant: str | None
    notes: str | None
    frequency: RecurringFrequency
    anchor_date: date_
    last_posted_date: date_ | None
    is_active: bool


class AppSettingsBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    # Defaulted so a backup exported before these thresholds existed still
    # imports cleanly under the same format version.
    negative_cash_flow_threshold_months: int = 2
    net_worth_decline_threshold_months: int = 2
    # Defaulted so a backup exported before this threshold existed still
    # imports cleanly under the same format version.
    risky_allocation_threshold_percent: int = 20


class BackupPayload(BaseModel):
    """A full, portable snapshot of every table. `aurum_backup_version` is
    checked on import so an incompatible/future file is rejected cleanly
    instead of half-applied."""

    aurum_backup_version: int
    exported_at: datetime
    app_version: str
    accounts: list[AccountBackup]
    categories: list[CategoryBackup]
    transactions: list[TransactionBackup]
    assets: list[AssetBackup]
    asset_valuations: list[AssetValuationBackup]
    # Defaulted so a backup exported before budgets existed still imports
    # cleanly under the same format version.
    budgets: list[BudgetBackup] = Field(default_factory=list)
    # Defaulted so a backup exported before goals existed still imports
    # cleanly under the same format version.
    goals: list[GoalBackup] = Field(default_factory=list)
    goal_contributions: list[GoalContributionBackup] = Field(default_factory=list)
    # Defaulted so a backup exported before recurring transactions existed
    # still imports cleanly under the same format version.
    recurring_transactions: list[RecurringTransactionBackup] = Field(default_factory=list)
    # Defaulted so a backup exported before the currency setting existed
    # still imports cleanly under the same format version.
    app_settings: AppSettingsBackup = Field(default_factory=lambda: AppSettingsBackup(currency="USD"))
