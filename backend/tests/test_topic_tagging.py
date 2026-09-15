import pytest

from app.models import BillTag, Event, SubjectMapping, Tag
from app.models.tag import GOVERNANCE_SLUG
from app.pipeline.topic_tagging import (
    assign_tags_for_bill,
    resolve_tag_for_subject,
    set_bill_tag_active,
)


@pytest.fixture()
def governance_tag(db_session):
    tag = Tag(slug=GOVERNANCE_SLUG, label="Governance", active=True)
    db_session.add(tag)
    db_session.commit()
    return tag


@pytest.fixture()
def housing_tag(db_session):
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    return tag


@pytest.fixture()
def taxes_tag(db_session):
    tag = Tag(slug="taxes_budget", label="Taxes/Budget", active=True)
    db_session.add(tag)
    db_session.commit()
    return tag


def test_resolve_tag_for_subject_uses_mapping(db_session, housing_tag, governance_tag):
    db_session.add(SubjectMapping(raw_subject="AFFORDABLE HOUSING", tag_id=housing_tag.id))
    db_session.commit()

    resolved = resolve_tag_for_subject(db_session, "AFFORDABLE HOUSING")
    assert resolved.slug == "housing"


def test_resolve_tag_for_subject_falls_back_to_governance(db_session, governance_tag):
    resolved = resolve_tag_for_subject(db_session, "SOME BRAND NEW SUBJECT NEVER SEEN")
    assert resolved.slug == GOVERNANCE_SLUG


def test_resolve_tag_for_subject_raises_without_governance_seeded(db_session):
    with pytest.raises(RuntimeError, match="Governance"):
        resolve_tag_for_subject(db_session, "ANYTHING")


def test_assign_tags_for_bill_creates_bill_tag_and_event(db_session, bill_factory, housing_tag, governance_tag):
    entity = bill_factory()
    db_session.add(SubjectMapping(raw_subject="AFFORDABLE HOUSING", tag_id=housing_tag.id))
    db_session.commit()

    created = assign_tags_for_bill(db_session, entity.id, raw_subjects=["AFFORDABLE HOUSING"])

    assert len(created) == 1
    assert created[0].tag_id == housing_tag.id
    assert created[0].tag_source == "legiscan"
    assert created[0].raw_subject == "AFFORDABLE HOUSING"
    assert created[0].active is True

    events = db_session.query(Event).filter(Event.entity_id == entity.id).all()
    assert len(events) == 1
    assert events[0].event_type == "tag_added"
    assert events[0].attributes["tag_slug"] == "housing"


def test_assign_tags_for_bill_is_idempotent(db_session, bill_factory, housing_tag, governance_tag):
    entity = bill_factory()
    db_session.add(SubjectMapping(raw_subject="AFFORDABLE HOUSING", tag_id=housing_tag.id))
    db_session.commit()

    first = assign_tags_for_bill(db_session, entity.id, raw_subjects=["AFFORDABLE HOUSING"])
    second = assign_tags_for_bill(db_session, entity.id, raw_subjects=["AFFORDABLE HOUSING"])

    assert len(first) == 1
    assert len(second) == 0  # already tagged, no duplicate row or event
    assert db_session.query(BillTag).filter(BillTag.bill_entity_id == entity.id).count() == 1
    assert db_session.query(Event).filter(Event.entity_id == entity.id).count() == 1


def test_assign_tags_for_bill_multi_tag(db_session, bill_factory, housing_tag, taxes_tag, governance_tag):
    entity = bill_factory()
    db_session.add(SubjectMapping(raw_subject="AFFORDABLE HOUSING", tag_id=housing_tag.id))
    db_session.add(SubjectMapping(raw_subject="TAXATION", tag_id=taxes_tag.id))
    db_session.commit()

    created = assign_tags_for_bill(db_session, entity.id, raw_subjects=["AFFORDABLE HOUSING", "TAXATION"])

    assert {bt.tag_id for bt in created} == {housing_tag.id, taxes_tag.id}


def test_assign_tags_for_bill_unmapped_subject_routes_to_governance(db_session, bill_factory, governance_tag):
    entity = bill_factory()

    created = assign_tags_for_bill(db_session, entity.id, raw_subjects=["ABANDONED OR UNCLAIMED PROPERTY"])

    assert len(created) == 1
    assert created[0].tag_id == governance_tag.id
    assert created[0].raw_subject == "ABANDONED OR UNCLAIMED PROPERTY"


def test_assign_tags_for_bill_ollama_fallback_has_no_raw_subject(db_session, bill_factory, housing_tag):
    entity = bill_factory()

    created = assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing"])

    assert len(created) == 1
    assert created[0].tag_source == "ollama"
    assert created[0].raw_subject is None


def test_set_bill_tag_active_hides_and_logs_event(db_session, bill_factory, housing_tag):
    entity = bill_factory()
    created = assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing"])
    bill_tag_id = created[0].id

    updated = set_bill_tag_active(db_session, bill_tag_id, active=False)
    assert updated.active is False

    events = db_session.query(Event).filter(Event.entity_id == entity.id, Event.event_type == "tag_hidden").all()
    assert len(events) == 1


def test_set_bill_tag_active_reactivate_logs_event(db_session, bill_factory, housing_tag):
    entity = bill_factory()
    created = assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing"])
    bill_tag_id = created[0].id
    set_bill_tag_active(db_session, bill_tag_id, active=False)

    updated = set_bill_tag_active(db_session, bill_tag_id, active=True)
    assert updated.active is True

    events = (
        db_session.query(Event)
        .filter(Event.entity_id == entity.id, Event.event_type == "tag_reactivated")
        .all()
    )
    assert len(events) == 1


def test_set_bill_tag_active_noop_when_already_in_requested_state(db_session, bill_factory, housing_tag):
    entity = bill_factory()
    created = assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing"])
    bill_tag_id = created[0].id

    set_bill_tag_active(db_session, bill_tag_id, active=True)  # already active

    events = db_session.query(Event).filter(Event.entity_id == entity.id).all()
    assert len(events) == 1  # only the original tag_added, no spurious reactivate
