"""add user_id to accounts, categories, tags, budgets, goals, recurring_transactions, app_settings

Revision ID: a3f7c2e9b148
Revises: 5c9e2a7f1b34
Create Date: 2026-09-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f7c2e9b148'
down_revision: Union[str, None] = '5c9e2a7f1b34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_accounts_user_id', 'accounts', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_accounts_user_id', 'accounts', ['user_id'])

    op.add_column('categories', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_categories_user_id', 'categories', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_categories_user_id', 'categories', ['user_id'])

    # Tags move from a single global namespace to one namespace per user.
    op.drop_constraint('tags_name_key', 'tags', type_='unique')
    op.add_column('tags', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_tags_user_id', 'tags', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_unique_constraint('uq_tags_user_id_name', 'tags', ['user_id', 'name'])

    op.add_column('budgets', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_budgets_user_id', 'budgets', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_budgets_user_id', 'budgets', ['user_id'])

    op.add_column('goals', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_goals_user_id', 'goals', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_goals_user_id', 'goals', ['user_id'])

    op.add_column('recurring_transactions', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_recurring_transactions_user_id', 'recurring_transactions', 'users', ['user_id'], ['id'], ondelete='CASCADE'
    )
    op.create_index('ix_recurring_transactions_user_id', 'recurring_transactions', ['user_id'])

    op.add_column('app_settings', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_app_settings_user_id', 'app_settings', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_unique_constraint('uq_app_settings_user_id', 'app_settings', ['user_id'])


def downgrade() -> None:
    op.drop_constraint('uq_app_settings_user_id', 'app_settings', type_='unique')
    op.drop_constraint('fk_app_settings_user_id', 'app_settings', type_='foreignkey')
    op.drop_column('app_settings', 'user_id')

    op.drop_index('ix_recurring_transactions_user_id', table_name='recurring_transactions')
    op.drop_constraint('fk_recurring_transactions_user_id', 'recurring_transactions', type_='foreignkey')
    op.drop_column('recurring_transactions', 'user_id')

    op.drop_index('ix_goals_user_id', table_name='goals')
    op.drop_constraint('fk_goals_user_id', 'goals', type_='foreignkey')
    op.drop_column('goals', 'user_id')

    op.drop_index('ix_budgets_user_id', table_name='budgets')
    op.drop_constraint('fk_budgets_user_id', 'budgets', type_='foreignkey')
    op.drop_column('budgets', 'user_id')

    op.drop_constraint('uq_tags_user_id_name', 'tags', type_='unique')
    op.drop_constraint('fk_tags_user_id', 'tags', type_='foreignkey')
    op.drop_column('tags', 'user_id')
    op.create_unique_constraint('tags_name_key', 'tags', ['name'])

    op.drop_index('ix_categories_user_id', table_name='categories')
    op.drop_constraint('fk_categories_user_id', 'categories', type_='foreignkey')
    op.drop_column('categories', 'user_id')

    op.drop_index('ix_accounts_user_id', table_name='accounts')
    op.drop_constraint('fk_accounts_user_id', 'accounts', type_='foreignkey')
    op.drop_column('accounts', 'user_id')
