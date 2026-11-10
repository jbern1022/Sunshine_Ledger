"""add federal bill texts and place findings

Revision ID: c6f2a9d4e8b3
Revises: b8e3f1a6d2c5
Create Date: 2026-11-10 04:06:06.440547

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c6f2a9d4e8b3'
down_revision: Union[str, None] = 'b8e3f1a6d2c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('federal_bill_texts',
    sa.Column('bill_entity_id', sa.UUID(), nullable=False),
    sa.Column('version_type', sa.String(length=100), nullable=True),
    sa.Column('version_date', sa.Date(), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('text_hash', sa.String(length=64), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['bill_entity_id'], ['entities.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bill_entity_id', 'source_url', name='uq_federal_bill_texts_source')
    )
    op.create_index(op.f('ix_federal_bill_texts_bill_entity_id'), 'federal_bill_texts', ['bill_entity_id'], unique=False)
    op.create_table('federal_place_findings',
    sa.Column('bill_entity_id', sa.UUID(), nullable=False),
    sa.Column('text_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('matched_term', sa.String(length=200), nullable=False),
    sa.Column('counties', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('section', sa.String(length=200), nullable=True),
    sa.Column('quote_text', sa.Text(), nullable=False),
    sa.Column('char_start', sa.Integer(), nullable=False),
    sa.Column('char_end', sa.Integer(), nullable=False),
    sa.Column('method_version', sa.String(length=40), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['bill_entity_id'], ['entities.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['text_id'], ['federal_bill_texts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('text_id', 'char_start', 'char_end', 'matched_term', name='uq_federal_place_findings_span')
    )
    op.create_index(op.f('ix_federal_place_findings_bill_entity_id'), 'federal_place_findings', ['bill_entity_id'], unique=False)
    op.create_index(op.f('ix_federal_place_findings_text_id'), 'federal_place_findings', ['text_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_federal_place_findings_text_id'), table_name='federal_place_findings')
    op.drop_index(op.f('ix_federal_place_findings_bill_entity_id'), table_name='federal_place_findings')
    op.drop_table('federal_place_findings')
    op.drop_index(op.f('ix_federal_bill_texts_bill_entity_id'), table_name='federal_bill_texts')
    op.drop_table('federal_bill_texts')
