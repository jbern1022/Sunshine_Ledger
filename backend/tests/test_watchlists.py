import uuid

import pytest

from app import account_data as ad
from app import watchlists as w
from app.models import Entity, Tag, User, Watch


def user(db, sub):
    u = User(cognito_sub=sub)
    db.add(u)
    db.commit()
    return u


def test_follow_a_bill_a_person_and_a_topic_and_list_them(db_session, bill_factory):
    u = user(db_session, "a")
    bill = bill_factory()
    person = Entity(entity_type="person", name="Pat Doe")
    db_session.add_all([person, Tag(slug="housing", label="Housing")])
    db_session.commit()
    w.add(db_session, u, "bill", str(bill.id))
    w.add(db_session, u, "official", str(person.id))
    w.add(db_session, u, "topic", "housing", "Duval County")
    assert [x.kind for x in w.listing(db_session, u)] == ["bill", "official", "topic"]
    assert [x.kind for x in w.listing(db_session, u, "topic")] == ["topic"]


def test_following_twice_is_idempotent_and_a_bill_id_is_not_an_official(db_session, bill_factory):
    u = user(db_session, "a")
    bill = bill_factory()
    first = w.add(db_session, u, "bill", str(bill.id))
    assert w.add(db_session, u, "bill", str(bill.id)).id == first.id
    assert db_session.query(Watch).count() == 1
    with pytest.raises(w.WatchError):
        w.add(db_session, u, "official", str(bill.id))  # right id, wrong kind


def test_rejects_unknown_targets_bad_kinds_and_jurisdiction_on_non_topics(db_session, bill_factory):
    u = user(db_session, "a")
    bill = bill_factory()
    for kind, target in (("bill", str(uuid.uuid4())), ("bill", "not-a-uuid"), ("topic", "nope"), ("color", "x")):
        with pytest.raises(w.WatchError):
            w.add(db_session, u, kind, target)
    with pytest.raises(w.WatchError):
        w.add(db_session, u, "bill", str(bill.id), "Duval County")


def test_the_cap_and_the_per_kind_switch(db_session, bill_factory, monkeypatch):
    u = user(db_session, "a")
    monkeypatch.setattr(w, "MAX_WATCHES", 2)
    bills = [bill_factory(bill_number=f"HB {i}") for i in range(3)]
    w.add(db_session, u, "bill", str(bills[0].id))
    w.add(db_session, u, "bill", str(bills[1].id))
    with pytest.raises(w.WatchError):
        w.add(db_session, u, "bill", str(bills[2].id))
    monkeypatch.setattr(w, "ENABLED_KINDS", frozenset({"bill", "topic"}))
    p = Entity(entity_type="person", name="Pat")
    db_session.add(p)
    db_session.commit()
    with pytest.raises(w.WatchError):
        w.add(db_session, u, "official", str(p.id))


def test_one_account_cannot_see_or_remove_anothers_watches(db_session, bill_factory):
    a, b = user(db_session, "a"), user(db_session, "b")
    bill = bill_factory()
    row = w.add(db_session, a, "bill", str(bill.id))
    assert w.listing(db_session, b) == []
    assert w.remove(db_session, b, row.id) is False
    assert db_session.query(Watch).count() == 1
    assert w.remove(db_session, a, row.id) is True


def test_export_includes_the_watchlist_and_deletion_removes_it(db_session, bill_factory):
    u = user(db_session, "a")
    w.add(db_session, u, "bill", str(bill_factory().id))
    assert ad.export_user(db_session, u)["watchlist"][0]["kind"] == "bill"
    ad.delete_account(db_session, u, lambda sub: None)
    assert db_session.query(Watch).count() == 0
