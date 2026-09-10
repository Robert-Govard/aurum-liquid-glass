"""make user_id NOT NULL on every multi-tenant table

Revision ID: 43a4507fff95
Revises: f91a3d5c7e42
Create Date: 2026-09-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '43a4507fff95'
down_revision: Union[str, None] = 'f91a3d5c7e42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every table this multi-tenant series added a nullable user_id to, in an
# order safe for deleting orphan (user_id IS NULL) rows: children before
# parents, respecting crypto_holdings -> crypto_portfolios's ON DELETE
# RESTRICT (a portfolio can't be deleted while it still has holdings).
# transaction_splits and goal_contributions are deliberately absent here —
# neither has a user_id column of its own (they're reached only through
# their already-listed parent, Transaction/Goal, and cascade-delete
# automatically when it does).
_DELETE_ORDER = [
    "asset_valuations",
    "crypto_transactions",
    "crypto_holdings",
    "crypto_portfolios",
    "budgets",
    "goals",
    "recurring_transactions",
    "transactions",
    "tags",
    "assets",
    "categories",
    "accounts",
    "app_settings",
    "crypto_sync_state",
]


def upgrade() -> None:
    conn = op.get_bind()
    # Pre-multi-tenant rows with no owner (seed/test data from before this
    # whole series began) — see this migration's own plan document for the
    # exact verification queries run against the dev database confirming
    # none of these are referenced by any properly-owned row.
    for table in _DELETE_ORDER:
        conn.execute(sa.text(f"DELETE FROM {table} WHERE user_id IS NULL"))

    for table in _DELETE_ORDER:
        op.alter_column(table, "user_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    # Reverses the schema change only — deleted orphan rows are NOT
    # restored. That deletion was a deliberate, irreversible data cleanup
    # (this migration's whole point), not a reversible schema edit.
    for table in reversed(_DELETE_ORDER):
        op.alter_column(table, "user_id", existing_type=sa.Integer(), nullable=True)
