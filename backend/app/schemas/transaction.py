from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import TransactionType
from app.schemas.account import AccountRead
from app.schemas.category import CategoryRead


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
    pass


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


class TransactionRead(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account: AccountRead
    category: CategoryRead | None = None


class TransactionPage(BaseModel):
    items: list[TransactionRead]
    total: int
    page: int
    page_size: int
