"""add office tenures

Revision ID: f2c8a5d7e1b9
Revises: e9b4d6a1c3f7
Create Date: 2026-11-10 03:40:33.578635

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f2c8a5d7e1b9'
down_revision: Union[str, None] = 'e9b4d6a1c3f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('office_tenures',
    sa.Column('person_entity_id', sa.UUID(), nullable=False),
    sa.Column('office_type', sa.String(length=12), nullable=False),
    sa.Column('state', sa.String(length=2), nullable=False),
    sa.Column('district', sa.Integer(), nullable=True),
    sa.Column('senate_class', sa.Integer(), nullable=True),
    sa.Column('party', sa.String(length=50), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('scheduled_end', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('end_reason', sa.String(length=20), nullable=True),
    sa.Column('end_reason_source_url', sa.Text(), nullable=True),
    sa.Column('official_url', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=60), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("end_reason IS NULL OR end_reason IN ('lost_general', 'lost_primary', 'term_limited', 'did_not_run', 'resigned', 'removed', 'died', 'other_office')", name='ck_office_tenures_reason'),
    sa.CheckConstraint("office_type IN ('us_house', 'us_senate', 'fl_house', 'fl_senate')", name='ck_office_tenures_office'),
    sa.CheckConstraint('end_reason IS NULL OR end_date IS NOT NULL', name='ck_office_tenures_reason_needs_end'),
    sa.ForeignKeyConstraint(['person_entity_id'], ['entities.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('person_entity_id', 'office_type', 'district', 'start_date', name='uq_office_tenures_term')
    )
    op.create_index(op.f('ix_office_tenures_office_type'), 'office_tenures', ['office_type'], unique=False)
    op.create_index(op.f('ix_office_tenures_person_entity_id'), 'office_tenures', ['person_entity_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_office_tenures_person_entity_id'), table_name='office_tenures')
    op.drop_index(op.f('ix_office_tenures_office_type'), table_name='office_tenures')
    op.drop_table('office_tenures')
