"""add source_checks

When each data source was last successfully checked, for the site's
"last checked" notes (GET /sources/status).

Revision ID: c4e7a2d9f1b3
Revises: b3c8e2f41a90
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c4e7a2d9f1b3'
down_revision: Union[str, None] = 'b3c8e2f41a90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'source_checks',
        sa.Column('source_key', sa.String(length=40), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_result', sa.String(length=200), nullable=True),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_key'),
    )


def downgrade() -> None:
    op.drop_table('source_checks')
