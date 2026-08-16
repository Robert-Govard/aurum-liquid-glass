"""add risk_level to assets

Revision ID: f2c8e4a917b3
Revises: e91b6d3c5a04
Create Date: 2026-08-16 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2c8e4a917b3'
down_revision: Union[str, None] = 'e91b6d3c5a04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### existing rows need a default or this NOT NULL column addition fails outright. ###
    op.add_column(
        'assets',
        sa.Column(
            'risk_level',
            sa.Enum('LOW', 'MEDIUM', 'HIGH', name='risk_level', native_enum=False, length=10),
            nullable=False,
            server_default='MEDIUM',
        ),
    )
    op.alter_column('assets', 'risk_level', server_default=None)


def downgrade() -> None:
    op.drop_column('assets', 'risk_level')
