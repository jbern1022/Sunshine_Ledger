"""add legiscan_call_counts

LegiScan API calls per month and operation, recorded by every run, so
month-to-date usage (10,000/month from 2026-10-01) is a query.

Revision ID: e5a1c3f7b9d2
Revises: d2b7e5f8a391
Create Date: 2026-09-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e5a1c3f7b9d2'
down_revision: Union[str, None] = 'd2b7e5f8a391'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'legiscan_call_counts',
        sa.Column('month', sa.Date(), nullable=False),
        sa.Column('operation', sa.String(length=40), nullable=False),
        sa.Column('calls', sa.Integer(), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('month', 'operation'),
    )


def downgrade() -> None:
    op.drop_table('legiscan_call_counts')
