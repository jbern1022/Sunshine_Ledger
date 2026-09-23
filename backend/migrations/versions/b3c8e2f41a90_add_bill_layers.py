"""add bill_layers, bill_layer_sources, bill_layer_reviews

Append-only storage for the Bill Says / Interpretation / Expected Effect
blocks on the bill page, their sources, and human reviews. See
docs/superpowers/specs/2026-09-23-bill-layers-design.md.

Revision ID: b3c8e2f41a90
Revises: a7d3f09c4b21
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b3c8e2f41a90'
down_revision: Union[str, None] = 'a7d3f09c4b21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PAIRS = (
    "(layer = 'bill_says' AND origin = 'bill_text') OR "
    "(layer = 'expected_effect' AND origin = 'legislative_staff') OR "
    "(layer = 'expected_effect' AND origin = 'sunshine_ledger_ai') OR "
    "(layer = 'interpretation' AND origin = 'legislative_staff') OR "
    "(layer = 'interpretation' AND origin = 'sunshine_ledger_ai')"
)


def upgrade() -> None:
    op.create_table(
        'bill_layers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('bill_entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('layer', sa.String(length=30), nullable=False),
        sa.Column('origin', sa.String(length=30), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('evidence_state', sa.String(length=30), nullable=False),
        sa.Column('scope_note', sa.Text(), nullable=False),
        sa.Column('items', postgresql.JSONB(), nullable=False),
        sa.Column('generated_by', sa.String(length=100), nullable=False),
        sa.Column('method_version', sa.String(length=80), nullable=False),
        sa.Column('input_hash', sa.String(length=64), nullable=False),
        sa.CheckConstraint(_PAIRS, name='ck_bill_layers_allowed_pair'),
        sa.CheckConstraint("evidence_state IN ('supported', 'insufficient_evidence')", name='ck_bill_layers_evidence_state'),
        sa.UniqueConstraint('bill_entity_id', 'layer', 'origin', 'version', name='uq_bill_layers_version'),
    )
    op.create_index('ix_bill_layers_bill_entity_id', 'bill_layers', ['bill_entity_id'])
    op.create_index(
        'uq_bill_layers_one_current', 'bill_layers', ['bill_entity_id', 'layer', 'origin'],
        unique=True, postgresql_where=sa.text('superseded_at IS NULL'),
    )
    op.create_table(
        'bill_layer_sources',
        sa.Column('bill_layer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('bill_layers.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sources.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'bill_layer_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('bill_layer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('bill_layers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('reviewer', sa.String(length=100), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.CheckConstraint("decision IN ('approved')", name='ck_bill_layer_reviews_decision'),
    )
    op.create_index('ix_bill_layer_reviews_bill_layer_id', 'bill_layer_reviews', ['bill_layer_id'])


def downgrade() -> None:
    op.drop_index('ix_bill_layer_reviews_bill_layer_id', table_name='bill_layer_reviews')
    op.drop_table('bill_layer_reviews')
    op.drop_table('bill_layer_sources')
    op.drop_index('uq_bill_layers_one_current', table_name='bill_layers')
    op.drop_index('ix_bill_layers_bill_entity_id', table_name='bill_layers')
    op.drop_table('bill_layers')
