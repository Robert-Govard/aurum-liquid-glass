"""Shared query-scoping helpers for per-user data isolation.

Every domain table a user can own (accounts, categories, tags, budgets,
goals, recurring transactions, app_settings, and more added by later
plans) carries a `user_id` column. Every service function that lists or
fetches rows from one of these tables routes through one of the two
helpers below instead of writing `.where(Model.user_id == ...)` by hand —
see the multi-tenant backend design spec's "Authorization / data
isolation" section for why: one place to get isolation right instead of
one per call site.
"""
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


def scoped(stmt: Select, model: type[ModelT], user_id: int) -> Select:
    """Adds a `WHERE model.user_id == user_id` clause to an existing
    select statement. Use for any list/filter query against a user-owned
    table."""
    return stmt.where(model.user_id == user_id)


async def get_owned_or_404(
    session: AsyncSession, model: type[ModelT], obj_id: int, user_id: int, detail: str = "Not found"
) -> ModelT:
    """Fetches one row by primary key AND owner in a single query — 404s
    if the row doesn't exist OR belongs to someone else. Deliberately the
    same response either way: confirming "that id exists, it's just not
    yours" would leak information a caller has no business learning.
    Replaces `session.get(Model, id)` wherever the table is user-owned."""
    result = await session.execute(select(model).where(model.id == obj_id, model.user_id == user_id))
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=detail)
    return obj
