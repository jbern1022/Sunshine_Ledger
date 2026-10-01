"""allow the who_it_affects layer in bill_layers

Adds (who_it_affects, sunshine_ledger_ai) to the allowed (layer, origin)
pairs. Rules: Data Model v1, "Scope and Affected Population" (2026-10-01).

Revision ID: f3b9d1a6c2e4
Revises: e5a1c3f7b9d2
Create Date: 2026-10-01

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f3b9d1a6c2e4'
down_revision: Union[str, None] = 'e5a1c3f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_PAIRS = (
    "(layer = 'bill_says' AND origin = 'bill_text') OR "
    "(layer = 'expected_effect' AND origin = 'legislative_staff') OR "
    "(layer = 'expected_effect' AND origin = 'sunshine_ledger_ai') OR "
    "(layer = 'interpretation' AND origin = 'legislative_staff') OR "
    "(layer = 'interpretation' AND origin = 'sunshine_ledger_ai')"
)
_NEW_PAIRS = _OLD_PAIRS + " OR (layer = 'who_it_affects' AND origin = 'sunshine_ledger_ai')"


def upgrade() -> None:
    op.drop_constraint('ck_bill_layers_allowed_pair', 'bill_layers', type_='check')
    op.create_check_constraint('ck_bill_layers_allowed_pair', 'bill_layers', _NEW_PAIRS)


def downgrade() -> None:
    op.execute("DELETE FROM bill_layers WHERE layer = 'who_it_affects'")
    op.drop_constraint('ck_bill_layers_allowed_pair', 'bill_layers', type_='check')
    op.create_check_constraint('ck_bill_layers_allowed_pair', 'bill_layers', _OLD_PAIRS)
