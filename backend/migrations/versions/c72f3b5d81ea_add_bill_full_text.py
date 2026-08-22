"""add bill full_text

Stores the cleaned text of the filed bill PDF, which is 10-75x longer than
the existing short `description`. Populated by pipeline/bill_text.py, which
costs one extra LegiScan API call per bill, so it is deliberately separate
from ordinary ingestion.

Revision ID: c72f3b5d81ea
Revises: 9a1c4e07b2f1
Create Date: 2026-08-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c72f3b5d81ea'
down_revision: Union[str, None] = '9a1c4e07b2f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bills', sa.Column('full_text', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('bills', 'full_text')
