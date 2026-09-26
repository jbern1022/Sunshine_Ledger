"""GET /sources/status and the ingestion steps' record_check."""

from datetime import datetime, timedelta, timezone

from app.api.sources import SOURCES, is_stale
from app.models import SourceCheck
from app.pipeline.source_checks import record_check

NOW = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
NIGHTLY = next(s for s in SOURCES if s.key == "legiscan")
WEEKLY = next(s for s in SOURCES if s.key == "gdelt")
BY_HAND = next(s for s in SOURCES if s.key == "census_bls")


def test_stale_rule():
    assert is_stale(NIGHTLY, None, NOW)
    assert not is_stale(NIGHTLY, NOW - timedelta(hours=30), NOW)
    assert is_stale(NIGHTLY, NOW - timedelta(hours=37), NOW)
    assert not is_stale(WEEKLY, NOW - timedelta(days=7), NOW)
    assert is_stale(WEEKLY, NOW - timedelta(days=9), NOW)
    assert not is_stale(BY_HAND, None, NOW)


def test_record_check_upserts_one_row_per_source(db_session):
    record_check(db_session, "legiscan", "0 bills changed or new")
    record_check(db_session, "legiscan", "3 bills changed or new")

    rows = db_session.query(SourceCheck).all()
    assert [(r.source_key, r.last_result) for r in rows] == [("legiscan", "3 bills changed or new")]


def test_status_lists_every_source_with_coverage_and_freshness(client, db_session, bill_factory):
    bill_factory()  # a legiscan bill with no full text
    record_check(db_session, "legiscan", "0 bills changed or new")

    body = {s["key"]: s for s in client.get("/sources/status").json()}

    assert list(body) == [s.key for s in SOURCES]
    assert body["legiscan"]["stale"] is False
    assert body["legiscan"]["last_checked_at"] is not None
    assert body["legiscan"]["bill_count"] >= 1
    assert body["iqm2_miami"]["stale"] is True  # never checked
    assert body["iqm2_miami"]["last_checked_at"] is None
    assert body["census_bls"]["stale"] is False
    assert body["gdelt"]["bill_count"] is None


def test_bill_list_items_carry_their_source_system(client, bill_factory):
    entity = bill_factory()
    item = next(b for b in client.get("/bills").json()["items"] if b["entity_id"] == str(entity.id))
    assert item["source_system"] == "legiscan"
