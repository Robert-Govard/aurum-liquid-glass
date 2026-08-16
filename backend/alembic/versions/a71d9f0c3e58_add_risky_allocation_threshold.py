"""add risky allocation threshold to app_settings

Revision ID: a71d9f0c3e58
Revises: f2c8e4a917b3
Create Date: 2026-08-16 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a71d9f0c3e58'
down_revision: Union[str, None] = 'f2c8e4a917b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'app_settings',
        sa.Column('risky_allocation_threshold_percent', sa.Integer(), nullable=False, server_default='20'),
    )
    op.alter_column('app_settings', 'risky_allocation_threshold_percent', server_default=None)


def downgrade() -> None:
    op.drop_column('app_settings', 'risky_allocation_threshold_percent')
