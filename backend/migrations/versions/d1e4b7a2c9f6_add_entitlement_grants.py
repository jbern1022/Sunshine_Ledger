"""add entitlement grants

Revision ID: d1e4b7a2c9f6
Revises: c6f2a9d4e8b3
Create Date: 2026-11-10 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd1e4b7a2c9f6'
down_revision: Union[str, None] = 'c6f2a9d4e8b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('entitlement_grants',
    sa.Column('subject', sa.String(length=120), nullable=False),
    sa.Column('package', sa.String(length=30), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('granted_by', sa.String(length=80), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_by', sa.String(length=80), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_entitlement_grants_subject_expires', 'entitlement_grants', ['subject', 'expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_entitlement_grants_subject_expires', table_name='entitlement_grants')
    op.drop_table('entitlement_grants')
