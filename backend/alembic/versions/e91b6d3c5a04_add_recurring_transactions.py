"""add recurring transactions

Revision ID: e91b6d3c5a04
Revises: d3f8a1c4b729
Create Date: 2026-08-16 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e91b6d3c5a04'
down_revision: Union[str, None] = 'd3f8a1c4b729'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'recurring_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('transfer_account_id', sa.Integer(), nullable=True),
        sa.Column(
            'type',
            sa.Enum('INCOME', 'EXPENSE', 'TRANSFER', name='recurring_transaction_type', native_enum=False, length=10),
            nullable=False,
        ),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('merchant', sa.String(length=150), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column(
            'frequency',
            sa.Enum('WEEKLY', 'MONTHLY', 'YEARLY', name='recurring_frequency', native_enum=False, length=10),
            nullable=False,
        ),
        sa.Column('anchor_date', sa.Date(), nullable=False),
        sa.Column('last_posted_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['transfer_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('recurring_transactions')
