"""Savings goals: CRUD for the goal itself, plus a running current_amount —
the sum of all logged GoalContribution rows, computed on read rather than
stored, so it's never out of sync with the log."""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal, GoalContribution
from app.schemas.goal import GoalContributionCreate, GoalCreate, GoalRead, GoalUpdate
from app.services.scoped import get_owned_or_404, scoped

_SELECT_WITH_TOTAL = (
    select(
        Goal.id,
        Goal.name,
        Goal.target_amount,
        Goal.target_date,
        func.coalesce(func.sum(GoalContribution.amount), 0).label("current_amount"),
    )
    .outerjoin(GoalContribution, GoalContribution.goal_id == Goal.id)
    .group_by(Goal.id, Goal.name, Goal.target_amount, Goal.target_date, Goal.created_at)
    .order_by(Goal.created_at)
)


def _to_read(row: Row) -> GoalRead:
    current = row.current_amount
    target = row.target_amount
    percent = float(current / target * 100) if target else 0.0
    return GoalRead(
        id=row.id,
        name=row.name,
        target_amount=target,
        target_date=row.target_date,
        current_amount=current,
        remaining=target - current,
        percent=percent,
        is_reached=current >= target,
    )


async def _read_one(session: AsyncSession, goal_id: int, user_id: int) -> GoalRead:
    stmt = scoped(_SELECT_WITH_TOTAL, Goal, user_id).where(Goal.id == goal_id)
    row = (await session.execute(stmt)).one()
    return _to_read(row)


async def list_goals(session: AsyncSession, user_id: int) -> list[GoalRead]:
    stmt = scoped(_SELECT_WITH_TOTAL, Goal, user_id)
    rows = (await session.execute(stmt)).all()
    return [_to_read(row) for row in rows]


async def create_goal(session: AsyncSession, payload: GoalCreate, user_id: int) -> GoalRead:
    goal = Goal(name=payload.name, target_amount=payload.target_amount, target_date=payload.target_date, user_id=user_id)
    session.add(goal)
    await session.commit()
    return GoalRead(
        id=goal.id,
        name=goal.name,
        target_amount=goal.target_amount,
        target_date=goal.target_date,
        current_amount=Decimal("0"),
        remaining=goal.target_amount,
        percent=0.0,
        is_reached=False,
    )


async def update_goal(session: AsyncSession, goal_id: int, payload: GoalUpdate, user_id: int) -> GoalRead:
    goal = await get_owned_or_404(session, Goal, goal_id, user_id, detail="Goal not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)
    await session.commit()
    return await _read_one(session, goal_id, user_id)


async def delete_goal(session: AsyncSession, goal_id: int, user_id: int) -> None:
    goal = await get_owned_or_404(session, Goal, goal_id, user_id, detail="Goal not found")
    await session.delete(goal)
    await session.commit()


async def add_contribution(
    session: AsyncSession, goal_id: int, payload: GoalContributionCreate, user_id: int
) -> GoalRead:
    goal = await get_owned_or_404(session, Goal, goal_id, user_id, detail="Goal not found")
    session.add(GoalContribution(goal_id=goal.id, amount=payload.amount, date=payload.date, note=payload.note))
    await session.commit()
    return await _read_one(session, goal_id, user_id)
