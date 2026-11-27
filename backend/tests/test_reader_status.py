"""D9 (docs/grant-ready/W1_BASELINE_2026-11-25.md): LegiScan leaves many ended
bills at "Introduced"/"Engrossed" after their final action. Bill pages already
read the real outcome from the last action (frontend/lib/displayStatus.ts);
the status filter and its counts must group bills the same way, or choosing
"Introduced" lists bills whose cards say "Died" or "Replaced by ...".
"""

import pytest

from app.api.reader_status import reader_status


def _bill(db_session, bill_factory, number, status, last_action):
    entity = bill_factory(bill_number=number, status=status)
    entity.bill.last_action = last_action
    db_session.commit()
    return entity


@pytest.mark.parametrize(
    "status,last_action,expected",
    [
        ("Introduced", "Laid on Table, refer to CS/HB 1219", "Replaced"),
        ("Introduced", "Laid on Table, refer CS/SB 7004", "Replaced"),
        ("Introduced", "Adopted, companion bill(s) passed, see HR 8087 (Adopted)", "Replaced"),
        ("Introduced", "Adopted by Publication", "Adopted"),
        ("Engrossed", "Died on Second Reading Calendar", "Died"),
        ("Introduced", "Died in Appropriations Committee", "Died"),
        ("Introduced", "Withdrawn prior to introduction", "Withdrawn"),
        ("Introduced", "Laid on Table", "Tabled"),
        ("Introduced", "Laid on Table.", "Tabled"),
        ("Introduced", "Referred to Rules", "Introduced"),
        ("Introduced", None, "Introduced"),
        ("Passed", "Died on Calendar", "Passed"),  # only Introduced/Engrossed are re-read
        ("Introduced", "Diedrich amendment adopted", "Introduced"),  # word boundary
    ],
)
def test_reader_status_python(status, last_action, expected):
    assert reader_status(status, last_action) == expected


def test_statuses_count_bills_as_readers_see_them(client, db_session, bill_factory):
    _bill(db_session, bill_factory, "HB 1", "Introduced", "Referred to Rules")
    _bill(db_session, bill_factory, "HB 2", "Introduced", "Died on Calendar")
    _bill(db_session, bill_factory, "HB 3", "Engrossed", "Died in Fiscal Policy")
    _bill(db_session, bill_factory, "HB 4", "Introduced", "Laid on Table, refer to CS/HB 9")
    _bill(db_session, bill_factory, "HB 5", "Passed", "Chapter No. 2026-1")

    body = client.get("/bills/statuses").json()
    assert {s["status"]: s["count"] for s in body} == {
        "Died": 2, "Introduced": 1, "Replaced": 1, "Passed": 1,
    }


def test_filter_introduced_leaves_out_ended_bills(client, db_session, bill_factory):
    _bill(db_session, bill_factory, "HB 1", "Introduced", "Referred to Rules")
    _bill(db_session, bill_factory, "HB 2", "Introduced", "Withdrawn from further consideration")

    body = client.get("/bills", params={"status": "Introduced"}).json()
    assert [b["bill_number"] for b in body["items"]] == ["HB 1"]


def test_filter_died_finds_bills_stored_as_introduced(client, db_session, bill_factory):
    _bill(db_session, bill_factory, "HB 1", "Introduced", "Died on Calendar")
    _bill(db_session, bill_factory, "HB 2", "Died", "Died in committee")  # a source that stores it
    _bill(db_session, bill_factory, "HB 3", "Introduced", "Referred to Rules")

    body = client.get("/bills", params={"status": "Died"}).json()
    assert sorted(b["bill_number"] for b in body["items"]) == ["HB 1", "HB 2"]


def test_list_item_carries_stored_status_unchanged(client, db_session, bill_factory):
    """The stored value stays in `status` (the card derives its own label)."""
    _bill(db_session, bill_factory, "HB 1", "Introduced", "Died on Calendar")
    item = client.get("/bills").json()["items"][0]
    assert item["status"] == "Introduced"
