"""dedupe then add UNIQUE(bill_entity_id, claim_type) on claims

Nothing at the DB level currently prevents two `what_it_does` claims for
the same bill -- dedup is purely application-level (input_hash checks in
summarize_batch.py), so a hash-check bug or a concurrent ingestion run
could silently accumulate duplicates, and the API's helper just takes
the first match it finds.

This can't safely be a bare `ADD CONSTRAINT` -- if duplicates already
exist in production, that statement fails outright and the deploy dies
mid-migration. So this: (1) for any (bill_entity_id, claim_type) group
with more than one row, deletes all but the most recently created one
-- claim_sources cascade-deletes with it, which is correct, since those
sources only ever backed the specific claim row being removed -- then
(2) adds the constraint. Verified against a from-scratch DB with no
duplicates (no-op dedupe, constraint applies cleanly) AND against a
synthetic duplicate scenario (3 claims in one group, correct survivor
kept, constraint applies after).

Whether production actually has duplicates today is unknown -- nothing
here can check that without DB access. If it does, this consolidates
them as a side effect of closing the gap; that's a real, if probably
small, data change worth being aware of before running this against
production, not a routine no-op migration.

Revision ID: b8e1d5a9f204
Revises: a1f4c9e2b6d3
Create Date: 2026-09-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e1d5a9f204'
down_revision: Union[str, None] = 'a1f4c9e2b6d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM claims
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY bill_entity_id, claim_type
                           ORDER BY created_at DESC, id DESC
                       ) AS rn
                FROM claims
            ) ranked
            WHERE rn > 1
        )
        """
    )
    op.create_unique_constraint(
        "uq_claims_bill_entity_id_claim_type", "claims", ["bill_entity_id", "claim_type"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_claims_bill_entity_id_claim_type", "claims", type_="unique")
