"""add users and auth sessions

Revision ID: e2f5c8b3d0a7
Revises: d1e4b7a2c9f6
Create Date: 2026-11-10 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e2f5c8b3d0a7'
down_revision: Union[str, None] = 'd1e4b7a2c9f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('cognito_sub', sa.String(length=80), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('mfa_required', sa.Boolean(), nullable=False),
    sa.Column('recovery_state', sa.String(length=14), nullable=False),
    sa.Column('last_sign_in_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cognito_sub')
    )
    op.create_table('auth_sessions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('idle_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('absolute_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('auth_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('factors', postgresql.ARRAY(sa.String(length=12)), nullable=False),
    sa.Column('restricted', sa.Boolean(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_reason', sa.String(length=40), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index('ix_auth_sessions_user', 'auth_sessions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_auth_sessions_user', table_name='auth_sessions')
    op.drop_table('auth_sessions')
    op.drop_table('users')
