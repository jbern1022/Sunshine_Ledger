"""add watches

Revision ID: f3a6d9c4e1b8
Revises: e2f5c8b3d0a7
Create Date: 2026-11-10 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f3a6d9c4e1b8'
down_revision: Union[str, None] = 'e2f5c8b3d0a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('watches',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('target', sa.String(length=80), nullable=False),
    sa.Column('jurisdiction', sa.String(length=80), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'kind', 'target', 'jurisdiction', name='uq_watches_user_target')
    )
    op.create_index(op.f('ix_watches_user_id'), 'watches', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_watches_user_id'), table_name='watches')
    op.drop_table('watches')
