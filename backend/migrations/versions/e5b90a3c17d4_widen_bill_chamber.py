"""widen bills.chamber

`chamber` was sized for "House"/"Senate" but in practice holds the
deliberative body handling a bill, which at city level is a committee name.
Jacksonville has 11 bodies longer than 50 characters (longest 87), so the
column overflowed and crashed nightly ingestion. Truncating would mangle a
quarter of Jacksonville's committee names in a field the UI displays, so
widen instead.

200 leaves real headroom over the observed maximum. Widening a varchar in
PostgreSQL doesn't rewrite the table, so this is cheap and safe.

Revision ID: e5b90a3c17d4
Revises: c72f3b5d81ea
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b90a3c17d4'
down_revision: Union[str, None] = 'c72f3b5d81ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'bills', 'chamber',
        existing_type=sa.String(length=50),
        type_=sa.String(length=200),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Narrowing can fail on rows that now exceed 50 chars, so truncate first
    # rather than leaving the downgrade to error out.
    op.execute("UPDATE bills SET chamber = left(chamber, 50) WHERE length(chamber) > 50")
    op.alter_column(
        'bills', 'chamber',
        existing_type=sa.String(length=200),
        type_=sa.String(length=50),
        existing_nullable=True,
    )
