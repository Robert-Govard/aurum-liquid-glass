"""add premium_until to users

Revision ID: b2f6c3d8e451
Revises: a1e4a2f9c318
Create Date: 2026-09-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f6c3d8e451'
down_revision: Union[str, None] = 'a1e4a2f9c318'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, no backfill needed — NULL is exactly "Free", which is what
    # every existing user should be after this migration (same pattern as
    # last_login_at's own migration).
    op.add_column('users', sa.Column('premium_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'premium_until')
