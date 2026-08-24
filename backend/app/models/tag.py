"""A free-form, reusable label on transactions — orthogonal to Category:
a category answers "what kind of spend is this", a tag answers "which
event/project does it belong to" (e.g. "trip:georgia", "tax-deductible").
A transaction can carry any number of tags, a tag can be reused across any
number of transactions — see transaction_tags below.
"""
from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

transaction_tags = Table(
    "transaction_tags",
    Base.metadata,
    Column("transaction_id", ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    transactions: Mapped[list["Transaction"]] = relationship(secondary=transaction_tags, back_populates="tags")
