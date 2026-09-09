"""add user_id to transactions

Revision ID: e7c4a9f1b620
Revises: a3f7c2e9b148
Create Date: 2026-09-09 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c4a9f1b620'
down_revision: Union[str, None] = 'a3f7c2e9b148'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_transactions_user_id', 'transactions', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_transactions_user_id', 'transactions', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_transactions_user_id', table_name='transactions')
    op.drop_constraint('fk_transactions_user_id', 'transactions', type_='foreignkey')
    op.drop_column('transactions', 'user_id')
