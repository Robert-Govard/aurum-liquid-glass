from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CategoryKind


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: CategoryKind
    icon: str | None = None
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int = 0
    # Subcategory parent, one level deep only — routes/categories.py rejects
    # a parent that itself already has a parent.
    parent_id: int | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int | None = None
    # The route uses exclude_unset=True, so sending parent_id explicitly as
    # null (as opposed to omitting the field) is what turns a subcategory
    # back into a top-level category.
    parent_id: int | None = None


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_default: bool
