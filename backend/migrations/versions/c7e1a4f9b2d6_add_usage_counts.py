"""add usage counts (daily totals, no identifiers)

Revision ID: c7e1a4f9b2d6
Revises: b6d9a2f4c1e7
Create Date: 2026-11-25 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c7e1a4f9b2d6'
down_revision: Union[str, None] = 'b6d9a2f4c1e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'usage_counts',
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('event', sa.String(length=20), nullable=False),
        sa.Column('page_kind', sa.String(length=20), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('day', 'event', 'page_kind'),
    )


def downgrade() -> None:
    op.drop_table('usage_counts')
