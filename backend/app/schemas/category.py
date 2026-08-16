from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CategoryKind


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: CategoryKind
    icon: str | None = None
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int | None = None


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_default: bool
