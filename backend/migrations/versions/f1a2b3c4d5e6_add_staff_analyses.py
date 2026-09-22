"""add staff_analyses table

Stores nonpartisan FL legislative-staff bill analyses, one row per
committee-stop analysis (a bill can have several over its life). Populated
by pipeline/staff_analysis.py, discovered via LegiScan's getBill
`supplements` array and fetched via the getSupplement op.

Revision ID: f1a2b3c4d5e6
Revises: 9c3e5b0a2f77
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = '9c3e5b0a2f77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'staff_analyses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'entity_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('entities.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('legiscan_supplement_id', sa.Integer(), nullable=False),
        sa.Column('committee', sa.String(length=300), nullable=True),
        sa.Column('analysis_date', sa.Date(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('legiscan_url', sa.Text(), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.UniqueConstraint('legiscan_supplement_id', name='uq_staff_analyses_legiscan_supplement_id'),
    )
    op.create_index('ix_staff_analyses_entity_id', 'staff_analyses', ['entity_id'])


def downgrade() -> None:
    op.drop_index('ix_staff_analyses_entity_id', table_name='staff_analyses')
    op.drop_table('staff_analyses')
