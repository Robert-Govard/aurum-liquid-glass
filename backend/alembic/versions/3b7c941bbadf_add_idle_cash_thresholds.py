"""add idle cash thresholds to app_settings

Revision ID: 3b7c941bbadf
Revises: a71d9f0c3e58
Create Date: 2026-08-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b7c941bbadf'
down_revision: Union[str, None] = 'a71d9f0c3e58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'app_settings',
        sa.Column('idle_cash_threshold_amount', sa.Numeric(14, 2), nullable=False, server_default='1000'),
    )
    op.add_column(
        'app_settings',
        sa.Column('idle_cash_threshold_days', sa.Integer(), nullable=False, server_default='60'),
    )
    op.alter_column('app_settings', 'idle_cash_threshold_amount', server_default=None)
    op.alter_column('app_settings', 'idle_cash_threshold_days', server_default=None)


def downgrade() -> None:
    op.drop_column('app_settings', 'idle_cash_threshold_days')
    op.drop_column('app_settings', 'idle_cash_threshold_amount')
