"""add last_login_at to users

Revision ID: 5f8a1bc05518
Revises: 43a4507fff95
Create Date: 2026-09-11 14:12:42.174187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f8a1bc05518'
down_revision: Union[str, None] = '43a4507fff95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'last_login_at')
