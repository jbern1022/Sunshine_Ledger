from datetime import date

from app.models import Event
from app.pipeline.amendments import fetch_amendment_text, sync_bill_amendments


class FakeAmendmentClient:
    def __init__(self, docs: dict[int, dict]):
        self.docs = docs
        self.calls: list[int] = []

    def get_amendment(self, amendment_id: int) -> dict:
        self.calls.append(amendment_id)
        return self.docs[amendment_id]


def test_sync_bill_amendments_writes_one_event_per_amendment(db_session, bill_factory):
    entity = bill_factory()
    amendments = [
        {"amendment_id": 111, "date": "2026-02-10", "chamber": "House", "adopted": 1, "title": "Amendment 1"},
        {"amendment_id": 222, "date": "2026-02-15", "chamber": "Senate", "adopted": 0, "title": "Amendment 2"},
    ]

    written = sync_bill_amendments(db_session, bill_entity=entity, amendments=amendments)
    db_session.commit()

    assert written == 2
    events = db_session.query(Event).filter_by(entity_id=entity.id, event_type="AMENDED").order_by(Event.title).all()
    assert len(events) == 2
    assert events[0].attributes["amendment_id"] == 111
    assert events[0].attributes["adopted"] is True
    assert events[0].event_date == date(2026, 2, 10)
    assert events[1].attributes["adopted"] is False


def test_sync_bill_amendments_is_idempotent_on_amendment_id(db_session, bill_factory):
    entity = bill_factory()
    amendments = [{"amendment_id": 111, "date": "2026-02-10", "chamber": "House", "adopted": 1, "title": "Amendment 1"}]

    sync_bill_amendments(db_session, bill_entity=entity, amendments=amendments)
    db_session.commit()
    written_second_run = sync_bill_amendments(db_session, bill_entity=entity, amendments=amendments)
    db_session.commit()

    assert written_second_run == 0
    events = db_session.query(Event).filter_by(entity_id=entity.id, event_type="AMENDED").all()
    assert len(events) == 1


def test_sync_bill_amendments_skips_entries_with_no_amendment_id(db_session, bill_factory):
    entity = bill_factory()
    written = sync_bill_amendments(db_session, bill_entity=entity, amendments=[{"date": "2026-02-10"}])
    db_session.commit()

    assert written == 0
    assert db_session.query(Event).filter_by(entity_id=entity.id, event_type="AMENDED").count() == 0


def test_sync_bill_amendments_handles_empty_list(db_session, bill_factory):
    entity = bill_factory()
    assert sync_bill_amendments(db_session, bill_entity=entity, amendments=[]) == 0


def test_fetch_amendment_text_decodes_html_document():
    import base64

    html = "<html><body><p>1 Section 1. Test amendment text.</p></body></html>"
    encoded = base64.b64encode(html.encode("utf-8")).decode("ascii")
    client = FakeAmendmentClient({111: {"doc": encoded, "mime": "text/html"}})

    text = fetch_amendment_text(client, 111)

    assert text is not None
    assert "Test amendment text." in text
    assert client.calls == [111]


def test_fetch_amendment_text_returns_none_for_unsupported_mime():
    import base64

    encoded = base64.b64encode(b"binary content").decode("ascii")
    client = FakeAmendmentClient({111: {"doc": encoded, "mime": "application/msword"}})

    assert fetch_amendment_text(client, 111) is None


def test_fetch_amendment_text_returns_none_when_doc_missing():
    client = FakeAmendmentClient({111: {"mime": "text/html"}})
    assert fetch_amendment_text(client, 111) is None
