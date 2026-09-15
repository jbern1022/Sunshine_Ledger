"""add bill topic tagging: tags, subject_mappings, bill_tags

Roadmap Phase 2 feature (Todoist 6hRpvJ6J3H3FmQ6G): curated badge taxonomy
for bills, with a raw-subject mapping table and a multi-tag join table.
Depends on the events table (already present via the unified bill_events
ADR) for logging tag_added/tag_hidden/tag_reactivated state changes -- no
schema change needed there, tagging just writes rows to the existing table.

Revision ID: d4a6e21c9f57
Revises: b8e1d5a9f204
Create Date: 2026-09-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a6e21c9f57'
down_revision: Union[str, None] = 'b8e1d5a9f204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tags',
        sa.Column('slug', sa.String(length=50), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index(op.f('ix_tags_slug'), 'tags', ['slug'], unique=True)

    op.create_table(
        'subject_mappings',
        sa.Column('raw_subject', sa.String(length=200), nullable=False),
        sa.Column('tag_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('raw_subject'),
    )
    op.create_index(op.f('ix_subject_mappings_raw_subject'), 'subject_mappings', ['raw_subject'], unique=True)

    op.create_table(
        'bill_tags',
        sa.Column('bill_entity_id', sa.UUID(), nullable=False),
        sa.Column('tag_id', sa.UUID(), nullable=False),
        sa.Column('tag_source', sa.String(length=20), nullable=False),
        sa.Column('raw_subject', sa.String(length=200), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bill_entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bill_entity_id', 'tag_id', name='uq_bill_tags_bill_entity_id_tag_id'),
    )
    op.create_index(op.f('ix_bill_tags_bill_entity_id'), 'bill_tags', ['bill_entity_id'], unique=False)
    op.create_index(op.f('ix_bill_tags_tag_id'), 'bill_tags', ['tag_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_bill_tags_tag_id'), table_name='bill_tags')
    op.drop_index(op.f('ix_bill_tags_bill_entity_id'), table_name='bill_tags')
    op.drop_table('bill_tags')

    op.drop_index(op.f('ix_subject_mappings_raw_subject'), table_name='subject_mappings')
    op.drop_table('subject_mappings')

    op.drop_index(op.f('ix_tags_slug'), table_name='tags')
    op.drop_table('tags')
