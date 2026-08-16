"""add alert thresholds to app_settings

Revision ID: b4e7c1a9f203
Revises: 9f3a2d7c5e11
Create Date: 2026-08-16 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e7c1a9f203'
down_revision: Union[str, None] = '9f3a2d7c5e11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'app_settings',
        sa.Column('negative_cash_flow_threshold_months', sa.Integer(), nullable=False, server_default='2'),
    )
    op.add_column(
        'app_settings',
        sa.Column('net_worth_decline_threshold_months', sa.Integer(), nullable=False, server_default='2'),
    )
    op.alter_column('app_settings', 'negative_cash_flow_threshold_months', server_default=None)
    op.alter_column('app_settings', 'net_worth_decline_threshold_months', server_default=None)


def downgrade() -> None:
    op.drop_column('app_settings', 'net_worth_decline_threshold_months')
    op.drop_column('app_settings', 'negative_cash_flow_threshold_months')
