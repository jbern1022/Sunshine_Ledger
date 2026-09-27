"""add bill_text_versions

Earlier text versions of a bill (e.g. as filed), for showing what changed
between the filed bill and the version that passed. bills.full_text stays
the latest version.

Revision ID: d2b7e5f8a391
Revises: c4e7a2d9f1b3
Create Date: 2026-09-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd2b7e5f8a391'
down_revision: Union[str, None] = 'c4e7a2d9f1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bill_text_versions',
        sa.Column('bill_entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('legiscan_doc_id', sa.Integer(), nullable=False),
        sa.Column('version_type', sa.String(length=100), nullable=True),
        sa.Column('version_date', sa.Date(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bill_entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('legiscan_doc_id'),
    )
    op.create_index('ix_bill_text_versions_bill_entity_id', 'bill_text_versions', ['bill_entity_id'])


def downgrade() -> None:
    op.drop_index('ix_bill_text_versions_bill_entity_id', table_name='bill_text_versions')
    op.drop_table('bill_text_versions')
