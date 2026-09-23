"""add flags.resolved_at

Records when a flag left "pending", so reporter emails can be deleted 90
days after resolution -- the promise on the public privacy page, enforced
by pipeline/purge_flag_emails.py. Flags resolved before this column existed
have no real resolution time, so they are backfilled with the migration
time: their 90-day clock starts now instead of being purged on the first
run.

Revision ID: a7d3f09c4b21
Revises: f1a2b3c4d5e6
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d3f09c4b21'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('flags', sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_flags_resolved_at'), 'flags', ['resolved_at'], unique=False)
    op.execute("UPDATE flags SET resolved_at = now() WHERE status <> 'pending'")


def downgrade() -> None:
    op.drop_index(op.f('ix_flags_resolved_at'), table_name='flags')
    op.drop_column('flags', 'resolved_at')
