from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.tag import Tag
from app.schemas.tag import TagCreate, TagRead

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagRead])
async def list_tags(session: AsyncSession = Depends(get_session)) -> list[Tag]:
    result = await session.execute(select(Tag).order_by(Tag.name))
    return list(result.scalars().all())


@router.post("", response_model=TagRead, status_code=201)
async def create_tag(payload: TagCreate, session: AsyncSession = Depends(get_session)) -> Tag:
    # Case-insensitive dedup — the frontend's tag picker creates tags
    # on the fly as the user types, so "Georgia" and "georgia" typed on two
    # different transactions should end up as the same tag, not two.
    name = payload.name.strip()
    existing = await session.execute(select(Tag).where(func.lower(Tag.name) == name.lower()))
    tag = existing.scalar_one_or_none()
    if tag is not None:
        return tag
    tag = Tag(name=name)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(tag_id: int, session: AsyncSession = Depends(get_session)) -> None:
    tag = await session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    await session.delete(tag)
    await session.commit()
