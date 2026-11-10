"""add federal earmarks

Revision ID: b6d9a2f4c1e7
Revises: a5c8f1e6d3b0
Create Date: 2026-11-10 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b6d9a2f4c1e7'
down_revision: Union[str, None] = 'a5c8f1e6d3b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('federal_earmarks',
    sa.Column('fiscal_year', sa.Integer(), nullable=False),
    sa.Column('stage', sa.String(length=10), nullable=False),
    sa.Column('chamber', sa.String(length=6), nullable=False),
    sa.Column('member_last', sa.String(length=80), nullable=False),
    sa.Column('member_first', sa.String(length=80), nullable=True),
    sa.Column('district', sa.String(length=8), nullable=False),
    sa.Column('party', sa.String(length=10), nullable=True),
    sa.Column('subcommittee', sa.String(length=80), nullable=False),
    sa.Column('recipient', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('recipient_address', sa.Text(), nullable=True),
    sa.Column('amount', sa.Integer(), nullable=True),
    sa.Column('member_url', sa.Text(), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=False),
    sa.Column('person_entity_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['person_entity_id'], ['entities.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fiscal_year', 'stage', 'member_last', 'district', 'subcommittee', 'recipient', 'description', name='uq_federal_earmarks_row')
    )
    op.create_index(op.f('ix_federal_earmarks_district'), 'federal_earmarks', ['district'], unique=False)
    op.create_index(op.f('ix_federal_earmarks_fiscal_year'), 'federal_earmarks', ['fiscal_year'], unique=False)
    op.create_index(op.f('ix_federal_earmarks_person_entity_id'), 'federal_earmarks', ['person_entity_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_federal_earmarks_person_entity_id'), table_name='federal_earmarks')
    op.drop_index(op.f('ix_federal_earmarks_fiscal_year'), table_name='federal_earmarks')
    op.drop_index(op.f('ix_federal_earmarks_district'), table_name='federal_earmarks')
    op.drop_table('federal_earmarks')
