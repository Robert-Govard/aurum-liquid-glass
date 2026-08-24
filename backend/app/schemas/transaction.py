from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.text import capitalize_first_letter
from app.models.enums import TransactionType
from app.schemas.account import AccountRead
from app.schemas.category import CategoryRead
from app.schemas.tag import TagRead


class TransactionBase(BaseModel):
    account_id: int
    category_id: int | None = None
    transfer_account_id: int | None = None
    type: TransactionType
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    description: str = Field(min_length=1, max_length=255)
    merchant: str | None = Field(default=None, max_length=150)
    notes: str | None = None
    date: date_

    # Auto-capitalizes "траты на продукты" -> "Траты на продукты" so mixed
    # casing from quick manual entry doesn't need fixing by hand later.
    @field_validator("description")
    @classmethod
    def _capitalize_description(cls, value: str) -> str:
        return capitalize_first_letter(value)

    @model_validator(mode="after")
    def _validate_type_specific_fields(self) -> "TransactionBase":
        if self.type == TransactionType.TRANSFER and not self.transfer_account_id:
            raise ValueError("transfer_account_id is required for transfer transactions")
        if self.type == TransactionType.TRANSFER and self.transfer_account_id == self.account_id:
            raise ValueError("transfer_account_id must differ from account_id")
        if self.type != TransactionType.TRANSFER and self.transfer_account_id:
            raise ValueError("transfer_account_id is only valid for transfer transactions")
        if self.type == TransactionType.TRANSFER and self.category_id:
            raise ValueError("category_id is not valid for transfer transactions")
        return self


class TransactionCreate(TransactionBase):
    tag_ids: list[int] = Field(default_factory=list)


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    category_id: int | None = None
    transfer_account_id: int | None = None
    type: TransactionType | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    description: str | None = Field(default=None, min_length=1, max_length=255)
    merchant: str | None = Field(default=None, max_length=150)
    notes: str | None = None
    date: date_ | None = None
    # Omitted -> tags untouched; sent (even as []) -> replaces the full tag set.
    tag_ids: list[int] | None = None

    @field_validator("description")
    @classmethod
    def _capitalize_description(cls, value: str | None) -> str | None:
        return capitalize_first_letter(value) if value is not None else None


class TransactionRead(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account: AccountRead
    category: CategoryRead | None = None
    tags: list[TagRead] = Field(default_factory=list)


class TransactionPage(BaseModel):
    items: list[TransactionRead]
    total: int
    page: int
    page_size: int


class TransactionBulkCreate(BaseModel):
    """CSV import (see routes/transactions.py's /bulk): the frontend parses
    the file and maps its columns client-side, then sends already-shaped
    rows here. All-or-nothing — same failure semantics as backup restore, so
    a single bad row never leaves a partial import behind."""

    items: list[TransactionCreate] = Field(min_length=1, max_length=5000)


class TransactionBulkCreateResult(BaseModel):
    created: int
