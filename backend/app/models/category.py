"""A spending/income category, colored so it maps 1:1 to a dashboard chart slot."""
from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CategoryKind


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[CategoryKind] = mapped_column(
        Enum(CategoryKind, name="category_kind", native_enum=False, length=10), nullable=False
    )
    # Lucide icon name rendered in the frontend (kept as a plain string so new
    # icons don't require a migration).
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Hex color drawn from the dataviz skill's validated categorical palette.
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    # Fixed slot ordering keeps the donut chart's category order stable across renders.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
