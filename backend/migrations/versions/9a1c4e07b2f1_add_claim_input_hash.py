"""add claim input_hash

Lets the summarization batch job tell "already summarized from this exact
input" apart from "summarized earlier from different input", so it can skip
the former (cost) and refresh the latter (staleness).

Nullable on purpose: existing claims predate the column and have no known
input, so they stay null and are treated as needing a refresh.

Revision ID: 9a1c4e07b2f1
Revises: 73c38cab2d74
Create Date: 2026-08-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1c4e07b2f1'
down_revision: Union[str, None] = '73c38cab2d74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('claims', sa.Column('input_hash', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_claims_input_hash'), 'claims', ['input_hash'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_claims_input_hash'), table_name='claims')
    op.drop_column('claims', 'input_hash')
