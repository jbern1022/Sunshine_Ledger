"""add pending alerts

Revision ID: a5c8f1e6d3b0
Revises: f3a6d9c4e1b8
Create Date: 2026-11-10 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a5c8f1e6d3b0'
down_revision: Union[str, None] = 'f3a6d9c4e1b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('pending_alerts',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('watch_id', sa.UUID(), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['watch_id'], ['watches.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'event_id', name='uq_pending_alerts_user_event')
    )
    op.create_index(op.f('ix_pending_alerts_user_id'), 'pending_alerts', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_pending_alerts_user_id'), table_name='pending_alerts')
    op.drop_table('pending_alerts')
