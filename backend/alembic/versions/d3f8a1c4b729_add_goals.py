"""add goals

Revision ID: d3f8a1c4b729
Revises: c7a5f9e2b816
Create Date: 2026-08-16 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3f8a1c4b729'
down_revision: Union[str, None] = 'c7a5f9e2b816'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'goals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('target_amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'goal_contributions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('goal_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['goal_id'], ['goals.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('goal_contributions')
    op.drop_table('goals')
