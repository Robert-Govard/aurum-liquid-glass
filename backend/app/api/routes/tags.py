from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.tag import Tag
from app.models.user import User
from app.schemas.tag import TagCreate, TagRead
from app.services.scoped import get_owned_or_404, scoped

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagRead])
async def list_tags(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> list[Tag]:
    stmt = scoped(select(Tag), Tag, current_user.id).order_by(Tag.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=TagRead, status_code=201)
async def create_tag(
    payload: TagCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Tag:
    # Case-insensitive dedup within this user's own tags — the frontend's
    # tag picker creates tags on the fly as the user types, so "Georgia"
    # and "georgia" typed on two different transactions should end up as
    # the same tag, not two, but that dedup is per-user, not global.
    name = payload.name.strip()
    existing = await session.execute(
        select(Tag).where(func.lower(Tag.name) == name.lower(), Tag.user_id == current_user.id)
    )
    tag = existing.scalar_one_or_none()
    if tag is not None:
        return tag
    tag = Tag(name=name, user_id=current_user.id)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    tag = await get_owned_or_404(session, Tag, tag_id, current_user.id, detail="Tag not found")
    await session.delete(tag)
    await session.commit()
