"""Response/request shapes for /api/admin/users — never include
password_hash, deliberately."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    is_active: bool


class AdminUserRead(UserRead):
    """GET /api/admin/users only — /api/auth/me keeps using plain UserRead,
    deliberately never exposing these per-user stats about "yourself" via
    that shape (the normal dashboard is where a user sees their own
    numbers)."""

    last_login_at: datetime | None
    accounts_count: int
    transactions_count: int
    net_worth: Decimal
