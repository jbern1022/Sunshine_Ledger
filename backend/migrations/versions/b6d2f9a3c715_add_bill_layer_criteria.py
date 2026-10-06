"""add bill_layer_criteria and bill_layer_criteria_reviews

Impact Lens: structured criteria for who_it_affects entries, kept apart from
the (immutable) layer version they are derived from, plus append-only human
reviews. See the Notion design "Impact Lens Structured Criteria".

Revision ID: b6d2f9a3c715
Revises: a4c7e2b9d815
Create Date: 2026-10-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b6d2f9a3c715'
down_revision: Union[str, None] = 'a4c7e2b9d815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bill_layer_criteria',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('bill_layer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('bill_layers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entry_index', sa.Integer(), nullable=False),
        sa.Column('vocabulary_version', sa.Integer(), nullable=False),
        sa.Column('method_version', sa.String(length=80), nullable=False),
        sa.Column('generated_by', sa.String(length=100), nullable=False),
        sa.Column('criteria', postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint('bill_layer_id', 'entry_index', 'vocabulary_version', 'method_version', name='uq_bill_layer_criteria_version'),
    )
    op.create_index('ix_bill_layer_criteria_bill_layer_id', 'bill_layer_criteria', ['bill_layer_id'])
    op.create_table(
        'bill_layer_criteria_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('criteria_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('bill_layer_criteria.id', ondelete='CASCADE'), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('reviewer', sa.String(length=100), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.CheckConstraint("decision IN ('approved', 'rejected')", name='ck_bill_layer_criteria_reviews_decision'),
    )
    op.create_index('ix_bill_layer_criteria_reviews_criteria_id', 'bill_layer_criteria_reviews', ['criteria_id'])
    op.create_index(
        'uq_bill_layer_criteria_reviews_one_approval', 'bill_layer_criteria_reviews', ['criteria_id'],
        unique=True, postgresql_where=sa.text("decision = 'approved'"),
    )


def downgrade() -> None:
    op.drop_index('uq_bill_layer_criteria_reviews_one_approval', table_name='bill_layer_criteria_reviews')
    op.drop_index('ix_bill_layer_criteria_reviews_criteria_id', table_name='bill_layer_criteria_reviews')
    op.drop_table('bill_layer_criteria_reviews')
    op.drop_index('ix_bill_layer_criteria_bill_layer_id', table_name='bill_layer_criteria')
    op.drop_table('bill_layer_criteria')
