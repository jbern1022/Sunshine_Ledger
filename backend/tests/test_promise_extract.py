import json
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import ElectionWinner, PromiseItem, SiteSnapshot
from app.promises.crawler import Crawler
from app.promises.extract import chunks, extract_snapshot, parse_items, run, verify_item
from app.promises.sites import add_site

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
PAGE = (
    b"<html><body><h1>Jane Smith for House</h1>"
    b"<p>I will cut property taxes for every homeowner in our district.</p>"
    b"<p>Thank you to everyone who came to the picnic last Saturday afternoon.</p>"
    b"<p>We believe every child deserves a safe school, and I will fight to fund school safety.</p></body></html>"
)


class FakeClient:
    model = "fake"

    def __init__(self, items):
        self.items = items
        self.calls = 0

    def generate(self, prompt, *, json_mode=False):
        self.calls += 1
        return json.dumps({"items": self.items})


def _snapshot(db, tmp_path, body=PAGE):
    w = ElectionWinner(cycle=2026, chamber="house", district=1, name="Jane Smith", result_status="unofficial",
                       source_url="u", source_retrieved_at=NOW, change_log=[])
    db.add(w)
    db.flush()
    site = add_site(db, w, "https://jane.example/", kind="campaign", discovered_via="manual", now=NOW)
    c = Crawler(db, storage_dir=str(tmp_path), now=lambda: NOW, sleep=lambda s: None)
    digest, rel = c._store(body)
    snap = SiteSnapshot(site_id=site.id, url=site.url, page_kind="home", status="ok", fetched_at=NOW,
                        content_hash=digest, storage_path=rel, byte_length=len(body))
    db.add(snap)
    db.flush()
    return snap


def test_only_exact_quotes_survive(db_session, tmp_path):
    snap = _snapshot(db_session, tmp_path)
    client = FakeClient([
        {"quote": "I will cut property taxes for every homeowner in our district.", "type": "commitment", "topics": ["housing", "not_a_topic"]},
        {"quote": "I will lower property taxes for all homeowners in the district.", "type": "commitment"},  # paraphrase
        {"quote": "We believe every child deserves a safe school, and I will fight to fund school safety.", "type": "bogus"},
        {"quote": "too short", "type": "commitment"},
    ])
    stats = extract_snapshot(db_session, snap, PAGE, client, now=NOW)
    assert stats == {"proposed": 4, "kept": 2, "rejected_not_found": 1, "rejected_length": 1, "duplicate": 0}
    items = db_session.execute(select(PromiseItem).order_by(PromiseItem.char_start)).scalars().all()
    assert [i.quote_text for i in items] == [
        "I will cut property taxes for every homeowner in our district.",
        "We believe every child deserves a safe school, and I will fight to fund school safety.",
    ]
    first, second = items
    assert first.review_state == "unreviewed" and first.source_url == "https://jane.example/"
    assert first.auto_labels["topics"] == ["housing"] and first.auto_labels["automated"] is True
    assert second.auto_labels["commitment_type"] == "other"
    assert snap.extracted_at == NOW
    assert all(verify_item(i, PAGE) for i in items)


def test_a_quote_must_match_byte_for_byte(db_session, tmp_path):
    snap = _snapshot(db_session, tmp_path)
    client = FakeClient([
        {"quote": "i will cut property taxes for every homeowner in our district.", "type": "commitment"},  # case
        {"quote": "I will cut property taxes for every homeowner in our district", "type": "commitment"},  # still a substring
    ])
    stats = extract_snapshot(db_session, snap, PAGE, client, now=NOW)
    assert stats["rejected_not_found"] == 1 and stats["kept"] == 1
    kept = db_session.execute(select(PromiseItem)).scalar_one()
    assert kept.quote_text == "I will cut property taxes for every homeowner in our district"


def test_same_quote_twice_is_one_item(db_session, tmp_path):
    snap = _snapshot(db_session, tmp_path)
    q = "I will cut property taxes for every homeowner in our district."
    stats = extract_snapshot(db_session, snap, PAGE, FakeClient([{"quote": q}, {"quote": q}]), now=NOW)
    assert stats["kept"] == 1 and stats["duplicate"] == 1


def test_run_processes_each_snapshot_once(db_session, tmp_path):
    snap = _snapshot(db_session, tmp_path)
    client = FakeClient([{"quote": "I will cut property taxes for every homeowner in our district."}])
    first = run(db_session, client, storage_dir=str(tmp_path))
    assert first["snapshots"] == 1 and first["kept"] == 1
    again = run(db_session, client, storage_dir=str(tmp_path))
    assert again["snapshots"] == 0 and client.calls == 1


def test_verify_item_catches_changed_text(db_session, tmp_path):
    snap = _snapshot(db_session, tmp_path)
    extract_snapshot(db_session, snap, PAGE, FakeClient([{"quote": "I will cut property taxes for every homeowner in our district."}]), now=NOW)
    item = db_session.execute(select(PromiseItem)).scalar_one()
    assert not verify_item(item, PAGE.replace(b"cut property taxes", b"raise property taxes"))


def test_parse_items_tolerates_noise():
    assert parse_items('noise {"items": [{"quote": "a b c"}, "x", {"nope": 1}]} tail') == [{"quote": "a b c"}]
    assert parse_items("not json") == []
    assert parse_items('[{"quote": "x"}]') == [{"quote": "x"}]


def test_chunks_split_on_lines():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(100))
    parts = chunks(text, size=500)
    assert len(parts) > 5 and "\n".join(parts) == text
