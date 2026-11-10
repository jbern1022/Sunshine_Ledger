"""map plan scope; allow us_house districts

Revision ID: b8e3f1a6d2c5
Revises: a5d9e2b7c4f1
Create Date: 2026-11-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b8e3f1a6d2c5'
down_revision: Union[str, None] = 'a5d9e2b7c4f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'map_plans',
        sa.Column('scope', sa.String(length=20), nullable=False, server_default='state_legislature'),
    )
    op.drop_constraint('ck_districts_chamber', 'districts', type_='check')
    op.create_check_constraint('ck_districts_chamber', 'districts', "chamber IN ('house', 'senate', 'us_house')")


def downgrade() -> None:
    op.drop_constraint('ck_districts_chamber', 'districts', type_='check')
    op.create_check_constraint('ck_districts_chamber', 'districts', "chamber IN ('house', 'senate')")
    op.drop_column('map_plans', 'scope')
