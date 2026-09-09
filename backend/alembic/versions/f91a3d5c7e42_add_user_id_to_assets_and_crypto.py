"""add user_id to assets, asset_valuations, crypto_portfolios, crypto_holdings, crypto_transactions, crypto_sync_state

Revision ID: f91a3d5c7e42
Revises: e7c4a9f1b620
Create Date: 2026-09-09 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f91a3d5c7e42'
down_revision: Union[str, None] = 'e7c4a9f1b620'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('assets', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_assets_user_id', 'assets', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_assets_user_id', 'assets', ['user_id'])

    op.add_column('asset_valuations', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_asset_valuations_user_id', 'asset_valuations', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_asset_valuations_user_id', 'asset_valuations', ['user_id'])

    op.add_column('crypto_portfolios', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_crypto_portfolios_user_id', 'crypto_portfolios', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_crypto_portfolios_user_id', 'crypto_portfolios', ['user_id'])

    op.add_column('crypto_holdings', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_crypto_holdings_user_id', 'crypto_holdings', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_crypto_holdings_user_id', 'crypto_holdings', ['user_id'])

    op.add_column('crypto_transactions', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_crypto_transactions_user_id', 'crypto_transactions', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_crypto_transactions_user_id', 'crypto_transactions', ['user_id'])

    op.add_column('crypto_sync_state', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_crypto_sync_state_user_id', 'crypto_sync_state', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_unique_constraint('uq_crypto_sync_state_user_id', 'crypto_sync_state', ['user_id'])


def downgrade() -> None:
    op.drop_constraint('uq_crypto_sync_state_user_id', 'crypto_sync_state', type_='unique')
    op.drop_constraint('fk_crypto_sync_state_user_id', 'crypto_sync_state', type_='foreignkey')
    op.drop_column('crypto_sync_state', 'user_id')

    op.drop_index('ix_crypto_transactions_user_id', table_name='crypto_transactions')
    op.drop_constraint('fk_crypto_transactions_user_id', 'crypto_transactions', type_='foreignkey')
    op.drop_column('crypto_transactions', 'user_id')

    op.drop_index('ix_crypto_holdings_user_id', table_name='crypto_holdings')
    op.drop_constraint('fk_crypto_holdings_user_id', 'crypto_holdings', type_='foreignkey')
    op.drop_column('crypto_holdings', 'user_id')

    op.drop_index('ix_crypto_portfolios_user_id', table_name='crypto_portfolios')
    op.drop_constraint('fk_crypto_portfolios_user_id', 'crypto_portfolios', type_='foreignkey')
    op.drop_column('crypto_portfolios', 'user_id')

    op.drop_index('ix_asset_valuations_user_id', table_name='asset_valuations')
    op.drop_constraint('fk_asset_valuations_user_id', 'asset_valuations', type_='foreignkey')
    op.drop_column('asset_valuations', 'user_id')

    op.drop_index('ix_assets_user_id', table_name='assets')
    op.drop_constraint('fk_assets_user_id', 'assets', type_='foreignkey')
    op.drop_column('assets', 'user_id')
