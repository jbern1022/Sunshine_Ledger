"""correction process: challenge fields on flags, correction_records, responses

The correction, dispute and right-of-reply process (Notion spec, decisions
agreed 2026-10-01). A flag becomes the spec's challenge: category, evidence,
target object and version, severity, Disputed timestamp, decision. Old
statuses map pending -> pending, reviewed -> decided, dismissed -> dismissed.

Revision ID: a4c7e2b9d815
Revises: f3b9d1a6c2e4
Create Date: 2026-10-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a4c7e2b9d815'
down_revision: Union[str, None] = 'f3b9d1a6c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('flags', sa.Column('object_type', sa.String(length=20), nullable=False, server_default='bill'))
    op.add_column('flags', sa.Column('object_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('flags', sa.Column('object_version', sa.Integer(), nullable=True))
    op.add_column('flags', sa.Column('category', sa.String(length=20), nullable=False, server_default='other'))
    op.add_column('flags', sa.Column('evidence_text', sa.Text(), nullable=True))
    op.add_column('flags', sa.Column('evidence_url', sa.String(length=2000), nullable=True))
    op.add_column('flags', sa.Column('is_named_party', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('flags', sa.Column('severity', sa.String(length=10), nullable=True))
    op.add_column('flags', sa.Column('disputed_since', sa.DateTime(timezone=True), nullable=True))
    op.add_column('flags', sa.Column('duplicate_of_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('flags', sa.Column('decision', sa.String(length=20), nullable=True))
    op.add_column('flags', sa.Column('decision_explanation', sa.Text(), nullable=True))
    op.add_column('flags', sa.Column('triaged_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('flags', sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key('fk_flags_duplicate_of', 'flags', 'flags', ['duplicate_of_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_flags_disputed_since', 'flags', ['disputed_since'])
    op.execute("UPDATE flags SET object_type = 'claim', object_id = claim_id WHERE claim_id IS NOT NULL")
    op.execute("UPDATE flags SET status = 'decided', decided_at = resolved_at WHERE status = 'reviewed'")
    op.create_check_constraint('ck_flags_status', 'flags', "status IN ('pending', 'triaged', 'decided', 'dismissed')")
    op.create_check_constraint('ck_flags_category', 'flags', "category IN ('factually_wrong', 'misleading', 'wrong_source', 'outdated', 'wrong_entity', 'other')")
    op.create_check_constraint('ck_flags_severity', 'flags', "severity IS NULL OR severity IN ('minor', 'material', 'critical')")
    op.create_check_constraint('ck_flags_decision', 'flags', "decision IS NULL OR decision IN ('update', 'correction', 'clarification', 'retraction', 'source_correction', 'no_change')")
    op.create_check_constraint('ck_flags_object_type', 'flags', "object_type IN ('bill', 'claim', 'bill_layer', 'amendment', 'vote', 'page_copy')")

    op.create_table(
        'correction_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('bill_entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('object_type', sa.String(length=20), nullable=False),
        sa.Column('object_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('prior_version', sa.Integer(), nullable=True),
        sa.Column('current_version', sa.Integer(), nullable=True),
        sa.Column('prior_text', sa.Text(), nullable=True),
        sa.Column('current_text', sa.Text(), nullable=True),
        sa.Column('change_type', sa.String(length=20), nullable=False),
        sa.Column('severity', sa.String(length=10), nullable=False),
        sa.Column('trigger', sa.String(length=20), nullable=False),
        sa.Column('flag_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('evidence_links', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('origin', sa.String(length=30), nullable=True),
        sa.Column('was_reviewed', sa.Boolean(), nullable=True),
        sa.Column('methodology_version', sa.String(length=80), nullable=True),
        sa.Column('decided_by', sa.String(length=100), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("change_type IN ('update', 'correction', 'clarification', 'retraction', 'source_correction')", name='ck_correction_change_type'),
        sa.CheckConstraint("severity IN ('minor', 'material', 'critical')", name='ck_correction_severity'),
        sa.CheckConstraint("trigger IN ('challenge', 'internal_review', 'source_change', 'methodology_change')", name='ck_correction_trigger'),
        sa.ForeignKeyConstraint(['bill_entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['flag_id'], ['flags.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_correction_records_bill_entity_id', 'correction_records', ['bill_entity_id'])

    op.create_table(
        'responses',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('bill_entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('object_type', sa.String(length=20), nullable=False),
        sa.Column('object_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('responder_name', sa.String(length=200), nullable=False),
        sa.Column('responder_role', sa.String(length=200), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('full_text_url', sa.String(length=2000), nullable=True),
        sa.Column('verified_via', sa.String(length=300), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('superseded_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['bill_entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['superseded_by_id'], ['responses.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_responses_bill_entity_id', 'responses', ['bill_entity_id'])


def downgrade() -> None:
    op.drop_index('ix_responses_bill_entity_id', table_name='responses')
    op.drop_table('responses')
    op.drop_index('ix_correction_records_bill_entity_id', table_name='correction_records')
    op.drop_table('correction_records')
    for ck in ('ck_flags_object_type', 'ck_flags_decision', 'ck_flags_severity', 'ck_flags_category', 'ck_flags_status'):
        op.drop_constraint(ck, 'flags', type_='check')
    op.execute("UPDATE flags SET status = 'reviewed' WHERE status = 'decided'")
    op.execute("UPDATE flags SET status = 'pending' WHERE status = 'triaged'")
    op.drop_index('ix_flags_disputed_since', table_name='flags')
    op.drop_constraint('fk_flags_duplicate_of', 'flags', type_='foreignkey')
    for col in ('decided_at', 'triaged_at', 'decision_explanation', 'decision', 'duplicate_of_id', 'disputed_since',
                'severity', 'is_named_party', 'evidence_url', 'evidence_text', 'category', 'object_version',
                'object_id', 'object_type'):
        op.drop_column('flags', col)
