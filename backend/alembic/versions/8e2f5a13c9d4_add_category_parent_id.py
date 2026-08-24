"""add category parent_id (subcategories)

Revision ID: 8e2f5a13c9d4
Revises: 3b7c941bbadf
Create Date: 2026-08-25 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e2f5a13c9d4'
down_revision: Union[str, None] = '3b7c941bbadf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('categories', sa.Column('parent_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_categories_parent_id_categories', 'categories', 'categories', ['parent_id'], ['id'], ondelete='SET NULL'
    )
    op.create_index('ix_categories_parent_id', 'categories', ['parent_id'])


def downgrade() -> None:
    op.drop_index('ix_categories_parent_id', table_name='categories')
    op.drop_constraint('fk_categories_parent_id_categories', 'categories', type_='foreignkey')
    op.drop_column('categories', 'parent_id')
