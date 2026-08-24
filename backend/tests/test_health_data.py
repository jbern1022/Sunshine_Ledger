"""Data-freshness endpoint tests.

/health stayed green through three days of stale data (Aug 21-24) because
liveness and freshness are different questions. These pin the second one.
"""

import datetime as dt

from app.models import Claim, Source


def _add_source(db, *, hours_ago: float):
    db.add(
        Source(
            url="https://example.com/doc",
            source_type="legiscan_bill",
            retrieved_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago),
        )
    )
    db.commit()


def _add_llm_claim(db, entity):
    db.add(
        Claim(
            bill_entity_id=entity.id,
            claim_type="what_it_does",
            claim_text="summary",
            generated_by="llm:llama3.1:8b",
        )
    )
    db.commit()


def _age_entity(db, entity, *, hours):
    entity.created_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    db.commit()


def test_liveness_stays_dependency_free(client):
    """/health must not start failing because the pipeline is behind -- it
    answers 'is the process up', nothing more."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_reports_stale_when_nothing_has_ever_been_ingested(client):
    resp = client.get("/health/data")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "stale"
    assert "no ingestion has ever run" in body["reasons"]


def test_healthy_when_ingestion_is_recent(client, db_session):
    _add_source(db_session, hours_ago=2)
    resp = client.get("/health/data")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["reasons"] == []


def test_stale_when_ingestion_is_too_old(client, db_session):
    """The failure mode this exists for: the process is fine, the data isn't."""
    _add_source(db_session, hours_ago=72)
    resp = client.get("/health/data")
    assert resp.status_code == 503
    assert "last ingestion was" in resp.json()["reasons"][0]


def test_one_missed_run_does_not_alert(client, db_session):
    """Threshold is 48h precisely so a single transient failure of a daily
    job doesn't page anyone."""
    _add_source(db_session, hours_ago=30)
    assert client.get("/health/data").status_code == 200


def test_flags_bills_stuck_without_a_summary(client, db_session, bill_factory):
    """45 bills sat ingested-but-unsummarized for three days without anything
    noticing."""
    _add_source(db_session, hours_ago=1)
    entity = bill_factory()
    entity.bill.description = "some text to summarize"
    db_session.commit()
    _age_entity(db_session, entity, hours=48)

    resp = client.get("/health/data")
    assert resp.status_code == 503
    assert resp.json()["bills_missing_summary"] == 1
    assert "have no summary" in resp.json()["reasons"][0]


def test_recently_ingested_bills_are_not_counted_as_stuck(client, db_session, bill_factory):
    """Scraping and summarizing run back-to-back in one job, so a bill
    without a summary mid-run is normal, not a fault."""
    _add_source(db_session, hours_ago=1)
    entity = bill_factory()
    entity.bill.description = "some text to summarize"
    db_session.commit()  # created_at is now, i.e. well inside the grace window

    resp = client.get("/health/data")
    assert resp.status_code == 200
    assert resp.json()["bills_missing_summary"] == 0


def test_summarized_bills_are_not_flagged(client, db_session, bill_factory):
    _add_source(db_session, hours_ago=1)
    entity = bill_factory()
    entity.bill.description = "some text"
    db_session.commit()
    _age_entity(db_session, entity, hours=48)
    _add_llm_claim(db_session, entity)

    resp = client.get("/health/data")
    assert resp.status_code == 200
    assert resp.json()["bills_missing_summary"] == 0


def test_bills_with_no_text_are_not_flagged(client, db_session, bill_factory):
    """Nothing to summarize isn't a pipeline failure."""
    _add_source(db_session, hours_ago=1)
    entity = bill_factory()
    entity.bill.description = None
    entity.bill.full_text = None
    db_session.commit()
    _age_entity(db_session, entity, hours=48)

    assert client.get("/health/data").status_code == 200


def test_payload_carries_the_numbers_a_human_needs(client, db_session):
    _add_source(db_session, hours_ago=5)
    body = client.get("/health/data").json()
    for key in ("last_ingest_at", "hours_since_ingest", "bills_total", "checked_at"):
        assert key in body
    assert 4 < body["hours_since_ingest"] < 6
