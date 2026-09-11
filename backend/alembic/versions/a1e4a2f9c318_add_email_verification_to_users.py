"""add email verification to users

Revision ID: a1e4a2f9c318
Revises: 5f8a1bc05518
Create Date: 2026-09-11 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1e4a2f9c318'
down_revision: Union[str, None] = '5f8a1bc05518'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every pre-existing account gets TRUE via the backfill default below —
    # only new registrations after this migration should ever start
    # unverified. Same two-step pattern as f2c8e4a917b3_add_risk_level_to_assets.py:
    # backfill existing rows with a server_default, then drop the default so
    # new inserts fall through to the model's own default=False.
    op.add_column('users', sa.Column('is_email_verified', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column('users', 'is_email_verified', server_default=None)
    op.add_column('users', sa.Column('email_verification_token_hash', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('email_verification_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'email_verification_expires_at')
    op.drop_column('users', 'email_verification_token_hash')
    op.drop_column('users', 'is_email_verified')
