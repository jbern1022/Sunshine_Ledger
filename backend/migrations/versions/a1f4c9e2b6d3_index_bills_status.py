"""index bills.status

`GET /bills` filters on `status` (see app/api/bills.py list_bills), and it
was unindexed. The other columns the originating task named turned out to
already be covered:

- claims.bill_entity_id already has index=True (app/models/claim.py).
- entities.jurisdiction_level/jurisdiction_name already has a composite
  index, ix_entities_jurisdiction (app/models/entity.py).
- There is no legislators table / district_id column in the current schema
  -- legislators are graph Entity rows, not a dedicated table.
- bills.chamber is not currently used as an API filter, so indexing it
  ahead of a real access pattern isn't justified yet.

Revision ID: a1f4c9e2b6d3
Revises: e5b90a3c17d4
Create Date: 2026-09-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f4c9e2b6d3'
down_revision: Union[str, None] = 'e5b90a3c17d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_bills_status', 'bills', ['status'])


def downgrade() -> None:
    op.drop_index('ix_bills_status', table_name='bills')
