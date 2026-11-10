"""add promise baseline tables

Revision ID: d7a3c1e8b5f2
Revises: b6d2f9a3c715
Create Date: 2026-11-10 03:30:13.632801

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd7a3c1e8b5f2'
down_revision: Union[str, None] = 'b6d2f9a3c715'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('election_winners',
    sa.Column('cycle', sa.Integer(), nullable=False),
    sa.Column('chamber', sa.String(length=10), nullable=False),
    sa.Column('district', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('party', sa.String(length=50), nullable=True),
    sa.Column('incumbent', sa.Boolean(), nullable=True),
    sa.Column('result_status', sa.String(length=12), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=False),
    sa.Column('source_retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('certified_at', sa.Date(), nullable=True),
    sa.Column('person_entity_id', sa.UUID(), nullable=True),
    sa.Column('change_log', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("chamber IN ('house', 'senate')", name='ck_election_winners_chamber'),
    sa.CheckConstraint("result_status IN ('unofficial', 'certified')", name='ck_election_winners_status'),
    sa.ForeignKeyConstraint(['person_entity_id'], ['entities.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cycle', 'chamber', 'district', name='uq_election_winners_seat')
    )
    op.create_index(op.f('ix_election_winners_cycle'), 'election_winners', ['cycle'], unique=False)
    op.create_index(op.f('ix_election_winners_person_entity_id'), 'election_winners', ['person_entity_id'], unique=False)
    op.create_table('official_sites',
    sa.Column('winner_id', sa.UUID(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('site_kind', sa.String(length=24), nullable=False),
    sa.Column('discovered_via', sa.String(length=24), nullable=False),
    sa.Column('discovered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('archive_url', sa.Text(), nullable=True),
    sa.Column('archive_timestamp', sa.String(length=14), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("discovered_via IN ('state_listing', 'official_member_page', 'directory', 'manual')", name='ck_official_sites_via'),
    sa.CheckConstraint("site_kind IN ('campaign', 'official_legislature', 'press')", name='ck_official_sites_kind'),
    sa.CheckConstraint("status IN ('unchecked', 'live', 'offline', 'blocked')", name='ck_official_sites_status'),
    sa.ForeignKeyConstraint(['winner_id'], ['election_winners.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('winner_id', 'url', name='uq_official_sites_winner_url')
    )
    op.create_index(op.f('ix_official_sites_winner_id'), 'official_sites', ['winner_id'], unique=False)
    op.create_table('site_snapshots',
    sa.Column('site_id', sa.UUID(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('page_kind', sa.String(length=24), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('http_status', sa.Integer(), nullable=True),
    sa.Column('final_url', sa.Text(), nullable=True),
    sa.Column('content_type', sa.String(length=200), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('byte_length', sa.Integer(), nullable=True),
    sa.Column('storage_path', sa.Text(), nullable=True),
    sa.Column('from_archive_timestamp', sa.String(length=14), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('ok', 'blocked_by_robots', 'unavailable', 'refused')", name='ck_site_snapshots_status'),
    sa.ForeignKeyConstraint(['site_id'], ['official_sites.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('site_id', 'url', 'content_hash', name='uq_site_snapshots_content')
    )
    op.create_index(op.f('ix_site_snapshots_fetched_at'), 'site_snapshots', ['fetched_at'], unique=False)
    op.create_index(op.f('ix_site_snapshots_site_id'), 'site_snapshots', ['site_id'], unique=False)
    op.create_table('promise_items',
    sa.Column('snapshot_id', sa.UUID(), nullable=False),
    sa.Column('winner_id', sa.UUID(), nullable=False),
    sa.Column('quote_text', sa.Text(), nullable=False),
    sa.Column('char_start', sa.Integer(), nullable=False),
    sa.Column('char_end', sa.Integer(), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=False),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('statement_date', sa.Date(), nullable=True),
    sa.Column('auto_labels', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('review_state', sa.String(length=20), nullable=False),
    sa.Column('reviewed_classification', sa.String(length=40), nullable=True),
    sa.Column('flag_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("review_state IN ('unreviewed', 'flagged', 'approved', 'rejected', 'not_a_commitment')", name='ck_promise_items_state'),
    sa.ForeignKeyConstraint(['snapshot_id'], ['site_snapshots.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['winner_id'], ['election_winners.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('snapshot_id', 'char_start', 'char_end', name='uq_promise_items_span')
    )
    op.create_index(op.f('ix_promise_items_review_state'), 'promise_items', ['review_state'], unique=False)
    op.create_index(op.f('ix_promise_items_snapshot_id'), 'promise_items', ['snapshot_id'], unique=False)
    op.create_index(op.f('ix_promise_items_winner_id'), 'promise_items', ['winner_id'], unique=False)
    op.create_table('promise_flags',
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('reason_text', sa.Text(), nullable=False),
    sa.Column('reporter_email', sa.String(length=320), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['promise_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_promise_flags_item_id'), 'promise_flags', ['item_id'], unique=False)
    op.create_table('promise_reviews',
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('reviewer', sa.String(length=100), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('classification', sa.String(length=40), nullable=True),
    sa.Column('from_state', sa.String(length=20), nullable=False),
    sa.Column('to_state', sa.String(length=20), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("action IN ('approve', 'reject', 'not_a_commitment', 'reclassify', 'unflag')", name='ck_promise_reviews_action'),
    sa.ForeignKeyConstraint(['item_id'], ['promise_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_promise_reviews_item_id'), 'promise_reviews', ['item_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_promise_reviews_item_id'), table_name='promise_reviews')
    op.drop_table('promise_reviews')
    op.drop_index(op.f('ix_promise_flags_item_id'), table_name='promise_flags')
    op.drop_table('promise_flags')
    op.drop_index(op.f('ix_promise_items_winner_id'), table_name='promise_items')
    op.drop_index(op.f('ix_promise_items_snapshot_id'), table_name='promise_items')
    op.drop_index(op.f('ix_promise_items_review_state'), table_name='promise_items')
    op.drop_table('promise_items')
    op.drop_index(op.f('ix_site_snapshots_site_id'), table_name='site_snapshots')
    op.drop_index(op.f('ix_site_snapshots_fetched_at'), table_name='site_snapshots')
    op.drop_table('site_snapshots')
    op.drop_index(op.f('ix_official_sites_winner_id'), table_name='official_sites')
    op.drop_table('official_sites')
    op.drop_index(op.f('ix_election_winners_person_entity_id'), table_name='election_winners')
    op.drop_index(op.f('ix_election_winners_cycle'), table_name='election_winners')
    op.drop_table('election_winners')
