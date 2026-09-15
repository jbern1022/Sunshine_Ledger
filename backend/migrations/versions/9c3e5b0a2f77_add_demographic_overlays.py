"""add demographic_overlays table

Roadmap Phase 2: ACS/BLS overlay for "who it affects" (Todoist
6hCMm77F28HRRr6p). Cached ACS/BLS data per geography + badge category --
see app/models/demographic_overlay.py for the full rationale.

Revision ID: 9c3e5b0a2f77
Revises: d4a6e21c9f57
Create Date: 2026-09-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9c3e5b0a2f77'
down_revision: Union[str, None] = 'd4a6e21c9f57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'demographic_overlays',
        sa.Column('geography_type', sa.String(length=20), nullable=False),
        sa.Column('geography_id', sa.String(length=200), nullable=False),
        sa.Column('badge_slug', sa.String(length=50), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('as_of', sa.String(length=20), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'geography_type', 'geography_id', 'badge_slug', 'source',
            name='uq_demographic_overlays_geography_badge_source',
        ),
    )
    op.create_index(op.f('ix_demographic_overlays_geography_type'), 'demographic_overlays', ['geography_type'], unique=False)
    op.create_index(op.f('ix_demographic_overlays_geography_id'), 'demographic_overlays', ['geography_id'], unique=False)
    op.create_index(op.f('ix_demographic_overlays_badge_slug'), 'demographic_overlays', ['badge_slug'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_demographic_overlays_badge_slug'), table_name='demographic_overlays')
    op.drop_index(op.f('ix_demographic_overlays_geography_id'), table_name='demographic_overlays')
    op.drop_index(op.f('ix_demographic_overlays_geography_type'), table_name='demographic_overlays')
    op.drop_table('demographic_overlays')
