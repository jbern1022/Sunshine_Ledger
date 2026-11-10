"""add map plans and districts

Revision ID: a5d9e2b7c4f1
Revises: f2c8a5d7e1b9
Create Date: 2026-11-10 03:47:22.991248

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5d9e2b7c4f1'
down_revision: Union[str, None] = 'f2c8a5d7e1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('map_plans',
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('state', sa.String(length=2), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('districts',
    sa.Column('map_plan_id', sa.UUID(), nullable=False),
    sa.Column('chamber', sa.String(length=10), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=10), nullable=False),
    sa.Column('spatial_context_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("chamber IN ('house', 'senate')", name='ck_districts_chamber'),
    sa.ForeignKeyConstraint(['map_plan_id'], ['map_plans.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['spatial_context_id'], ['spatial_contexts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('map_plan_id', 'code', name='uq_districts_plan_code')
    )
    op.create_index(op.f('ix_districts_chamber'), 'districts', ['chamber'], unique=False)
    op.create_index(op.f('ix_districts_code'), 'districts', ['code'], unique=False)
    op.create_index(op.f('ix_districts_map_plan_id'), 'districts', ['map_plan_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_districts_map_plan_id'), table_name='districts')
    op.drop_index(op.f('ix_districts_code'), table_name='districts')
    op.drop_index(op.f('ix_districts_chamber'), table_name='districts')
    op.drop_table('districts')
    op.drop_table('map_plans')
