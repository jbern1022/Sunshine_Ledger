from datetime import date
from pathlib import Path

from app.models import Event
from app.pipeline.flsenate_amendments import merge_amendments, parse_amendments

FIXTURE = (Path(__file__).parent / "fixtures" / "flsenate_hb1389_2026_amendments.html").read_text()


def test_parses_every_committee_and_floor_amendment_with_its_sponsor():
    rows = parse_amendments(FIXTURE)
    assert [(a.number, a.sponsor, a.stage) for a in rows] == [
        ("208403", "Redondo", "committee"),
        ("406455", "Redondo", "committee"),
        ("789001", "Duggan", "committee"),
        ("668106", "Calatayud", "floor"),
        ("680391", "Redondo", "floor"),
    ]
    first = rows[0]
    assert first.label == "Strike All Amendment"
    assert first.summary == "Remove everything after the enacting clause and insert:"
    assert first.filed == date(2026, 2, 10)
    assert (first.last_action, first.last_action_date) == ("Adopted without Objection", date(2026, 2, 11))
    assert first.bill_version == "H 1389 Filed"
    assert first.chamber == "House"
    assert first.pdf_url == "https://www.flsenate.gov/Session/Bill/2026/1389/Amendment/208403/PDF"
    assert first.adopted
    assert rows[2].label == "Amendment to Amendment (406455)"
    floor = rows[3]
    assert (floor.last_action, floor.last_action_date) == ("House: Concurred as Amended", date(2026, 3, 12))
    # Filed in the Senate (the Delete All), then concurred in by the House.
    assert floor.chamber == "Senate"
    assert floor.pdf_url.endswith("/Amendment/668106/PDF")


def test_adopted_reads_the_last_action():
    rows = parse_amendments(FIXTURE)
    a = rows[0]
    for action, adopted in [("Withdrawn", False), ("Not Adopted", False), ("Senate: Concurred", True), ("Pending", False)]:
        a.last_action = action
        assert a.adopted is adopted, action


def test_merge_adds_sponsors_to_legiscan_events_and_adds_the_missing_ones(db_session, bill_factory):
    bill = bill_factory(bill_number="H1389")
    legiscan = Event(entity_id=bill.id, event_type="AMENDED", event_date=date(2026, 2, 11),
                     title="House Committee Amendment #208403",
                     attributes={"amendment_id": 1, "chamber": "House", "adopted": False})
    db_session.add(legiscan)
    db_session.commit()

    updated, added = merge_amendments(db_session, bill, parse_amendments(FIXTURE))
    db_session.commit()
    assert (updated, added) == (1, 4)
    assert legiscan.attributes["sponsor"] == "Redondo"
    # The official last action ("Adopted without Objection") decides; LegiScan's
    # contradicting flag is kept for provenance.
    assert (legiscan.attributes["adopted"], legiscan.attributes["legiscan_adopted"]) == (True, False)
    assert legiscan.attributes["state_link"].endswith("/Amendment/208403/PDF")

    new = db_session.query(Event).filter(Event.entity_id == bill.id, Event.title.like("%#789001")).one()
    assert new.attributes["source"] == "flsenate"
    assert new.attributes["sponsor"] == "Duggan"
    assert new.title == "House Committee Amendment #789001"
    assert new.event_date == date(2026, 2, 24)

    # Rerunning changes nothing.
    assert merge_amendments(db_session, bill, parse_amendments(FIXTURE)) == (0, 0)


def test_page_without_amendments_parses_to_nothing():
    assert parse_amendments("<html><body><div id='tabBodyAmendments'></div></body></html>") == []


def test_legiscan_record_joins_the_flsenate_event_instead_of_duplicating(db_session, bill_factory):
    from app.pipeline.amendments import sync_bill_amendments

    bill = bill_factory(bill_number="H1389")
    merge_amendments(db_session, bill, parse_amendments(FIXTURE))
    db_session.commit()
    written = sync_bill_amendments(db_session, bill_entity=bill, amendments=[
        {"amendment_id": 99, "title": "House Committee Amendment #789001", "adopted": 1, "chamber": "H", "date": "2026-02-25"},
        {"amendment_id": 100, "title": "Senate Floor Amendment #111111", "adopted": 0, "chamber": "S", "date": "2026-03-01"},
    ])
    db_session.commit()
    assert written == 1  # only the amendment flsenate.gov didn't list
    twin = db_session.query(Event).filter(Event.title.like("%#789001")).one()
    assert (twin.attributes["amendment_id"], twin.attributes["sponsor"]) == (99, "Duggan")
    assert (twin.attributes["adopted"], twin.attributes["legiscan_adopted"]) == (True, True)
    assert db_session.query(Event).filter(Event.entity_id == bill.id, Event.event_type == "AMENDED").count() == 6


def test_bill_api_returns_sponsor_and_label(client, db_session, bill_factory):
    bill = bill_factory(bill_number="H1389")
    merge_amendments(db_session, bill, parse_amendments(FIXTURE))
    db_session.commit()
    amendments = client.get(f"/bills/{bill.id}").json()["amendments"]
    first = next(a for a in amendments if a["number"] == "208403")
    assert (first["sponsor"], first["label"], first["last_action"]) == (
        "Redondo", "Strike All Amendment", "Adopted without Objection")
