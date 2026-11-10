from datetime import date, datetime, timedelta, timezone

from app import alerts, watchlists as w
from app.models import BillTag, Entity, Event, PendingAlert, Relationship, Tag, User


def user(db, sub="a"):
    u = User(cognito_sub=sub)
    db.add(u)
    db.commit()
    return u


def event(db, bill, title="Referred to committee", etype="status_change", after=None):
    e = Event(entity_id=bill.id, event_type=etype, event_date=date(2026, 12, 2), title=title)
    db.add(e)
    db.commit()
    if after is not None:
        e.created_at = after
        db.commit()
    return e


def test_a_followed_bill_queues_only_changes_after_the_follow(db_session, bill_factory):
    u, bill = user(db_session), bill_factory()
    old = event(db_session, bill, "Filed")
    w.add(db_session, u, "bill", str(bill.id))
    assert alerts.generate(db_session) == 0  # history is not replayed
    new = event(db_session, bill, "Passed House")
    assert alerts.generate(db_session) == 1
    assert alerts.generate(db_session) == 0  # idempotent
    items = alerts.build_digest(db_session, u)
    assert [i.event_title for i in items] == ["Passed House"] and items[0].why == "You follow this bill"
    assert old.id != new.id


def test_an_official_matches_events_on_bills_they_sponsor_or_cosponsor_only(db_session, bill_factory):
    u = user(db_session)
    person = Entity(entity_type="person", name="Pat Doe")
    db_session.add(person)
    mine, other = bill_factory(bill_number="HB 1"), bill_factory(bill_number="HB 2")
    db_session.add_all([
        Relationship(from_entity_id=person.id, to_entity_id=mine.id, relationship_type="co_sponsor"),
    ])
    db_session.commit()
    w.add(db_session, u, "official", str(person.id))
    event(db_session, mine, "Amended")
    event(db_session, other, "Amended")
    assert alerts.generate(db_session) == 1
    assert alerts.build_digest(db_session, u)[0].why == "A bill sponsored by an official you follow"


def test_a_topic_can_be_limited_to_a_jurisdiction(db_session, bill_factory):
    u = user(db_session)
    tag = Tag(slug="housing", label="Housing")
    state_bill, city_bill = bill_factory(bill_number="HB 1"), bill_factory(bill_number="B-2")
    city_bill.jurisdiction_name = "Jacksonville"
    db_session.add(tag)
    db_session.flush()
    for b in (state_bill, city_bill):
        db_session.add(BillTag(bill_entity_id=b.id, tag_id=tag.id, tag_source="legiscan", active=True))
    db_session.commit()
    w.add(db_session, u, "topic", "housing", "Jacksonville")
    event(db_session, state_bill)
    event(db_session, city_bill)
    assert alerts.generate(db_session) == 1
    assert alerts.build_digest(db_session, u)[0].bill_entity_id == city_bill.id


def test_one_event_matching_two_watches_is_one_alert_and_inactive_users_get_none(db_session, bill_factory):
    u, gone = user(db_session, "a"), user(db_session, "b")
    bill = bill_factory()
    tag = Tag(slug="housing", label="Housing")
    db_session.add(tag)
    db_session.flush()
    db_session.add(BillTag(bill_entity_id=bill.id, tag_id=tag.id, tag_source="legiscan", active=True))
    db_session.commit()
    for x in (u, gone):
        w.add(db_session, x, "bill", str(bill.id))
    w.add(db_session, u, "topic", "housing")
    gone.status = "suspended"
    db_session.commit()
    event(db_session, bill)
    assert alerts.generate(db_session) == 1
    assert db_session.query(PendingAlert).count() == 1 and len(alerts.build_digest(db_session, u)) == 1


def test_delivery_is_recorded_only_for_this_users_rows(db_session, bill_factory):
    a, b = user(db_session, "a"), user(db_session, "b")
    bill = bill_factory()
    for x in (a, b):
        w.add(db_session, x, "bill", str(bill.id))
    event(db_session, bill)
    alerts.generate(db_session)
    ids = [i.alert_id for i in alerts.build_digest(db_session, a)]
    assert alerts.mark_delivered(db_session, b, ids) == 0  # not b's rows
    assert alerts.mark_delivered(db_session, a, ids) == 1
    assert alerts.build_digest(db_session, a) == [] and len(alerts.build_digest(db_session, b)) == 1
    assert alerts.mark_delivered(db_session, a, ids) == 0  # already delivered
