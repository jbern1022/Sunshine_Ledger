import pytest

from app.models import BillTag, Tag
from app.pipeline.topic_tagging_backfill import select_local_bills_needing_tags


@pytest.fixture()
def housing_tag(db_session):
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    return tag


def _make_local_bill(db_session, bill_factory, *, source_key: str, source_value: str = "1"):
    entity = bill_factory()
    entity.external_ids = {source_key: source_value}
    db_session.commit()
    return entity


def test_selects_legistar_bill_with_no_ollama_tag(db_session, bill_factory):
    entity = _make_local_bill(db_session, bill_factory, source_key="legistar_matter_id")

    candidates = select_local_bills_needing_tags(db_session)

    assert [c.id for c in candidates] == [entity.id]


def test_selects_iqm2_bill_with_no_ollama_tag(db_session, bill_factory):
    entity = _make_local_bill(db_session, bill_factory, source_key="iqm2_legi_file_id")

    candidates = select_local_bills_needing_tags(db_session)

    assert [c.id for c in candidates] == [entity.id]


def test_excludes_legiscan_bills(db_session, bill_factory):
    """A plain legiscan bill (bill_factory's default external_ids={}) is not
    a local bill and shouldn't be picked up by this backfill -- LegiScan
    tagging is a separate path with its own (currently empty, per the
    getBill verification ticket) data source."""
    bill_factory()

    assert select_local_bills_needing_tags(db_session) == []


def test_excludes_local_bills_already_ollama_tagged(db_session, bill_factory, housing_tag):
    entity = _make_local_bill(db_session, bill_factory, source_key="legistar_matter_id")
    db_session.add(BillTag(bill_entity_id=entity.id, tag_id=housing_tag.id, tag_source="ollama", active=True))
    db_session.commit()

    assert select_local_bills_needing_tags(db_session) == []


def test_does_not_exclude_a_local_bill_with_only_a_legiscan_tag(db_session, bill_factory, housing_tag):
    """Mirrors tag_local_bill's own guard scoping (tag_source="ollama"
    specifically) -- an unrelated tag_source shouldn't suppress backfill."""
    entity = _make_local_bill(db_session, bill_factory, source_key="legistar_matter_id")
    db_session.add(BillTag(bill_entity_id=entity.id, tag_id=housing_tag.id, tag_source="legiscan", active=True))
    db_session.commit()

    assert [c.id for c in select_local_bills_needing_tags(db_session)] == [entity.id]


def test_respects_limit(db_session, bill_factory):
    for _ in range(3):
        _make_local_bill(db_session, bill_factory, source_key="legistar_matter_id")

    assert len(select_local_bills_needing_tags(db_session, limit=2)) == 2


def test_state_bills_are_selected_only_with_include_state(db_session, bill_factory):
    state_bill = _make_local_bill(db_session, bill_factory, source_key="legiscan_id", source_value="2044116")

    assert select_local_bills_needing_tags(db_session) == []
    assert [e.id for e in select_local_bills_needing_tags(db_session, include_state=True)] == [state_bill.id]


def test_hide_redundant_governance_hides_only_alongside_a_specific_badge(db_session, bill_factory, housing_tag):
    from sqlalchemy import select

    from app.models import Event
    from app.pipeline.topic_tagging_backfill import hide_redundant_governance

    governance = Tag(slug="governance", label="Governance", active=True)
    db_session.add(governance)
    db_session.flush()
    both = _make_local_bill(db_session, bill_factory, source_key="legistar_matter_id", source_value="1")
    only_gov = _make_local_bill(db_session, bill_factory, source_key="legistar_matter_id", source_value="2")
    for bill, tag in [(both, governance), (both, housing_tag), (only_gov, governance)]:
        db_session.add(BillTag(bill_entity_id=bill.id, tag_id=tag.id, tag_source="ollama", active=True))
    db_session.commit()

    assert hide_redundant_governance(db_session) == 1  # dry run
    assert all(t.active for t in db_session.execute(select(BillTag)).scalars())

    assert hide_redundant_governance(db_session, apply=True) == 1
    active = {(t.bill_entity_id, t.tag.slug) for t in db_session.execute(select(BillTag)).scalars() if t.active}
    assert active == {(both.id, "housing"), (only_gov.id, "governance")}
    hidden = db_session.execute(select(Event).where(Event.event_type == "tag_hidden")).scalar_one()
    assert hidden.entity_id == both.id
