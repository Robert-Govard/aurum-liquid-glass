"""add app_settings

Revision ID: 9f3a2d7c5e11
Revises: 1152a14e9d55
Create Date: 2026-08-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f3a2d7c5e11'
down_revision: Union[str, None] = '1152a14e9d55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Singleton row (id=1) — app boot's seed_default_app_settings() also
    # get-or-creates it, but seeding it here means it exists immediately
    # after migrating, even before the app has started once.
    op.execute("INSERT INTO app_settings (id, currency) VALUES (1, 'USD')")


def downgrade() -> None:
    op.drop_table('app_settings')
