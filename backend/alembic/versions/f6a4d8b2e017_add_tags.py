"""add tags and transaction_tags

Revision ID: f6a4d8b2e017
Revises: 8e2f5a13c9d4
Create Date: 2026-08-25 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a4d8b2e017'
down_revision: Union[str, None] = '8e2f5a13c9d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'transaction_tags',
        sa.Column('transaction_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('transaction_id', 'tag_id'),
    )


def downgrade() -> None:
    op.drop_table('transaction_tags')
    op.drop_table('tags')
