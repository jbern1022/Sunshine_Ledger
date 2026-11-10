from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import ElectionWinner, OfficialSite, PromiseItem, PromiseReview, SiteSnapshot

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
AUTH = ("testadmin", "testpass")


@pytest.fixture()
def items(db_session):
    w = ElectionWinner(cycle=2026, chamber="house", district=3, name="Jane Smith", party="REP",
                       result_status="unofficial", source_url="u", source_retrieved_at=NOW, change_log=[])
    db_session.add(w)
    db_session.flush()
    site = OfficialSite(winner_id=w.id, url="https://jane.example/", site_kind="campaign",
                        discovered_via="manual", discovered_at=NOW, status="live")
    db_session.add(site)
    db_session.flush()
    snap = SiteSnapshot(site_id=site.id, url=site.url, page_kind="home", status="ok", fetched_at=NOW,
                        content_hash="a" * 64, storage_path="aa/x.html")
    db_session.add(snap)
    db_session.flush()
    out = []
    for n, ctype in enumerate(["commitment", "value_statement", "commitment"]):
        i = PromiseItem(snapshot_id=snap.id, winner_id=w.id, quote_text=f"I will do thing number {n} for you.",
                        char_start=n * 100, char_end=n * 100 + 30, source_url=snap.url, captured_at=NOW,
                        auto_labels={"automated": True, "commitment_type": ctype, "topics": ["housing"]})
        db_session.add(i)
        out.append(i)
    db_session.flush()
    return out


def test_public_list_is_verbatim_labelled_and_has_no_fulfillment(client, items):
    r = client.get("/promises?chamber=house&district=3")
    body = r.json()
    assert r.status_code == 200 and body["total"] == 3
    assert "No item says whether a promise was kept" in body["disclosure"]
    first = body["items"][0]
    assert first["quote"] == "I will do thing number 0 for you."
    assert first["review_label"] == "Unreviewed"
    assert first["snapshot"]["content_hash"] == "a" * 64
    assert first["official"]["name"] == "Jane Smith" and first["official"]["result_status"] == "unofficial"
    assert not any("fulfil" in k or "kept" in k for k in first)


def test_rejected_and_not_a_commitment_are_hidden(client, db_session, items):
    items[0].review_state = "rejected"
    items[1].review_state = "not_a_commitment"
    db_session.flush()
    assert client.get("/promises").json()["total"] == 1
    assert client.get(f"/promises/{items[0].id}").status_code == 404


def test_flagging_marks_the_item_and_counts(client, db_session, items):
    r = client.post(f"/promises/{items[1].id}/flag", json={"reason_text": "This is not what the page says"})
    assert r.status_code == 201 and r.json() == {"id": str(items[1].id), "review_state": "flagged", "flag_count": 1}
    assert client.get(f"/promises/{items[1].id}").json()["review_label"].startswith("Flagged")


def test_queue_needs_admin_and_orders_by_risk(client, items):
    assert client.get("/promises/admin/queue").status_code == 401
    client.post(f"/promises/{items[1].id}/flag", json={"reason_text": "out of context"})
    queue = client.get("/promises/admin/queue", auth=AUTH).json()
    ids = [i["id"] for i in queue["items"]]
    assert ids[0] == str(items[1].id)  # flagged first, even though it is only a value statement
    assert ids[1:] == [str(items[0].id), str(items[2].id)]  # then drafted commitments
    assert queue["items"][0]["open_flags"] == ["out of context"]


def test_review_actions_are_logged_and_close_flags(client, db_session, items):
    client.post(f"/promises/{items[0].id}/flag", json={"reason_text": "wrong person"})
    r = client.post(f"/promises/admin/{items[0].id}/review", auth=AUTH,
                    json={"action": "reject", "note": "Quote is from a guest post"})
    assert r.json()["review_state"] == "rejected"
    log = db_session.execute(select(PromiseReview)).scalar_one()
    assert (log.reviewer, log.from_state, log.to_state, log.note) == ("testadmin", "flagged", "rejected", "Quote is from a guest post")
    db_session.refresh(items[0])
    assert all(f.resolved_at for f in items[0].flags)
    assert client.get(f"/promises/{items[0].id}").status_code == 404


def test_approve_and_reclassify(client, db_session, items):
    client.post(f"/promises/admin/{items[2].id}/review", auth=AUTH, json={"action": "reclassify"} )
    assert client.post(f"/promises/admin/{items[2].id}/review", auth=AUTH, json={"action": "reclassify"}).status_code == 422
    r = client.post(f"/promises/admin/{items[2].id}/review", auth=AUTH, json={"action": "reclassify", "classification": "value_statement"})
    assert r.json()["classification"] == "value_statement" and r.json()["review_state"] == "unreviewed"
    client.post(f"/promises/admin/{items[2].id}/review", auth=AUTH, json={"action": "approve"})
    got = client.get(f"/promises/{items[2].id}").json()
    assert got["review_label"] == "Reviewed" and got["automated_labels"]["overridden_by_reviewer"] is True


def test_coverage_reports_gaps(client, db_session, items):
    db_session.add(ElectionWinner(cycle=2026, chamber="senate", district=9, name="No Site", result_status="unofficial",
                                  source_url="u", source_retrieved_at=NOW, change_log=[]))
    db_session.flush()
    c = client.get("/promises/coverage").json()
    assert c["winners"] == 2 and c["winners_without_a_site"] == 1 and c["winners_with_a_snapshot"] == 1
    assert c["statements_by_review_state"] == {"unreviewed": 3}
