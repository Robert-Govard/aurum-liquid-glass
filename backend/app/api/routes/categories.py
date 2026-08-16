from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.category import Category
from app.models.enums import CategoryKind
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
async def list_categories(
    kind: CategoryKind | None = None, session: AsyncSession = Depends(get_session)
) -> list[Category]:
    stmt = select(Category).order_by(Category.sort_order)
    if kind is not None:
        stmt = stmt.where(Category.kind == kind)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=CategoryRead, status_code=201)
async def create_category(payload: CategoryCreate, session: AsyncSession = Depends(get_session)) -> Category:
    category = Category(**payload.model_dump(), is_default=False)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int, payload: CategoryUpdate, session: AsyncSession = Depends(get_session)
) -> Category:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    await session.commit()
    await session.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: int, session: AsyncSession = Depends(get_session)) -> None:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if category.is_default:
        raise HTTPException(status_code=400, detail="Default categories cannot be deleted")
    await session.delete(category)
    await session.commit()
