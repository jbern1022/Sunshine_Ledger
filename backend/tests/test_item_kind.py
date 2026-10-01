from datetime import datetime, timezone

import pytest

from app.models import Source
from app.pipeline.item_kind import backfill_item_types, item_kind


@pytest.mark.parametrize(
    ("item_type", "kind"),
    [
        (None, "legislation"),
        ("Ordinance", "legislation"),
        ("PZAB Resolution", "legislation"),
        ("Discussion Item", "discussion"),
        ("Civil Service Discussion", "discussion"),
        ("CEB Agenda", "agenda"),
        ("Minutes", "agenda"),
        ("Protocol Item", "other"),
        ("Attorney-Client Session", "other"),
        ("Civil Service Notification", "other"),
    ],
)
def test_item_kind(item_type, kind):
    assert item_kind(item_type) == kind


def test_backfill_copies_the_newest_source_type(db_session, bill_factory):
    item = bill_factory(bill_number="19799", name="A DISCUSSION ON POLICING IN THE URBAN CORE.")
    item.jurisdiction_level, item.jurisdiction_name = "city", "Miami"
    item.external_ids = {"iqm2_legi_file_id": "19799"}
    for when, kind in [(datetime(2026, 9, 1, tzinfo=timezone.utc), "Resolution"),
                       (datetime(2026, 9, 20, tzinfo=timezone.utc), "Discussion Item")]:
        db_session.add(Source(url="https://miamifl.iqm2.com/x", source_type="iqm2_legislation", retrieved_at=when,
                              metadata_json={"legi_file_id": 19799, "type": kind}))
    db_session.commit()

    assert backfill_item_types(db_session) == 1
    assert item.attributes["item_type"] == "Discussion Item"
    assert backfill_item_types(db_session) == 0


def test_bill_list_reports_the_kind(client, db_session, bill_factory):
    item = bill_factory(bill_number="19799")
    item.attributes = {"item_type": "Discussion Item"}
    db_session.commit()
    row = client.get("/bills").json()["items"][0]
    assert (row["item_type"], row["item_kind"]) == ("Discussion Item", "discussion")
