"""add tag_quarantine and bill_tag_runs

Unknown tag slugs proposed by the local model are held for review instead of
dropped, and each classification records its input hash and outcome so an
amended bill is re-classified and a failed call is retried rather than
masked by a Governance fallback.

Revision ID: c8e3a1d7f5b2
Revises: b6d2f9a3c715
Create Date: 2026-10-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c8e3a1d7f5b2'
down_revision: Union[str, None] = 'b6d2f9a3c715'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tag_quarantine',
        sa.Column('bill_entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('proposed_slug', sa.String(length=100), nullable=False),
        sa.Column('tag_source', sa.String(length=20), nullable=False),
        sa.Column('bill_title', sa.String(length=300), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('mapped_tag_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewer', sa.String(length=100), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bill_entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['mapped_tag_id'], ['tags.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bill_entity_id', 'proposed_slug', name='uq_tag_quarantine_bill_slug'),
    )
    op.create_index('ix_tag_quarantine_bill_entity_id', 'tag_quarantine', ['bill_entity_id'])
    op.create_index('ix_tag_quarantine_proposed_slug', 'tag_quarantine', ['proposed_slug'])
    op.create_index('ix_tag_quarantine_status', 'tag_quarantine', ['status'])

    op.create_table(
        'bill_tag_runs',
        sa.Column('bill_entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('input_hash', sa.String(length=64), nullable=False),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('detail', sa.String(length=300), nullable=True),
        sa.Column('ran_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bill_entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bill_entity_id'),
    )


def downgrade() -> None:
    op.drop_table('bill_tag_runs')
    op.drop_index('ix_tag_quarantine_status', table_name='tag_quarantine')
    op.drop_index('ix_tag_quarantine_proposed_slug', table_name='tag_quarantine')
    op.drop_index('ix_tag_quarantine_bill_entity_id', table_name='tag_quarantine')
    op.drop_table('tag_quarantine')
