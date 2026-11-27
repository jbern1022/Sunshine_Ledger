from datetime import datetime, timedelta, timezone

from app.models import ElectionWinner, SiteSnapshot
from app.promises.changes import find_changes, main
from app.promises.crawler import Crawler
from app.promises.sites import add_site

T0 = datetime(2026, 11, 28, 4, tzinfo=timezone.utc)
V1 = b"<html><body><p>I will cut property taxes.</p><script>var n='a1';</script></body></html>"
V1_NONCE = b"<html><body><p>I will cut property taxes.</p><script>var n='b2';</script></body></html>"
V2 = b"<html><body><p>I will freeze property taxes.</p></body></html>"
V3 = b"<html><body><p>I will lower property taxes.</p></body></html>"


def _site(db, url="https://jane.example/"):
    w = ElectionWinner(cycle=2026, chamber="house", district=1, name="Jane Smith", result_status="unofficial",
                       source_url="u", source_retrieved_at=T0, change_log=[])
    db.add(w)
    db.flush()
    return add_site(db, w, url, kind="campaign", discovered_via="manual", now=T0)


def _fetch(db, tmp_path, site, body, at, *, url=None, archive=None, status="ok"):
    c = Crawler(db, storage_dir=str(tmp_path), now=lambda: at, sleep=lambda s: None)
    digest, rel = c._store(body)
    db.add(SiteSnapshot(site_id=site.id, url=url or site.url, page_kind="home", status=status, fetched_at=at,
                        content_hash=digest, storage_path=rel, byte_length=len(body), from_archive_timestamp=archive))
    db.flush()
    return digest


def _read(tmp_path):
    return lambda rel: (tmp_path / rel).read_bytes()


def test_a_reworded_page_is_a_change_that_needs_review(db_session, tmp_path):
    site = _site(db_session)
    h1 = _fetch(db_session, tmp_path, site, V1, T0)
    h2 = _fetch(db_session, tmp_path, site, V2, T0 + timedelta(days=7))
    [c] = find_changes(db_session, read_body=_read(tmp_path))
    assert (c["url"], c["old"]["sha256"], c["new"]["sha256"]) == ("https://jane.example/", h1, h2)
    assert c["old"]["vault_path"] == f"snapshots/{h1[:2]}/{h1}.html"
    assert c["new"]["fetched_at"] == "2026-12-05T04:00:00+00:00"
    assert (c["text_changed"], c["review"]) == (True, "needs review")


def test_markup_churn_is_recorded_but_not_flagged(db_session, tmp_path):
    site = _site(db_session)
    _fetch(db_session, tmp_path, site, V1, T0)
    _fetch(db_session, tmp_path, site, V1_NONCE, T0 + timedelta(days=1))
    [c] = find_changes(db_session, read_body=_read(tmp_path))
    assert (c["text_changed"], c["review"]) == (False, "markup only")


def test_unchanged_pages_other_urls_archives_and_failures_are_not_changes(db_session, tmp_path):
    site = _site(db_session)
    _fetch(db_session, tmp_path, site, V1, T0)
    _fetch(db_session, tmp_path, site, V2, T0 + timedelta(days=1), url="https://jane.example/issues")
    _fetch(db_session, tmp_path, site, V2, T0 + timedelta(days=2), archive="20261101000000")
    db_session.add(SiteSnapshot(site_id=site.id, url=site.url, page_kind="home", status="unavailable",
                                fetched_at=T0 + timedelta(days=3), note="HTTP 503"))
    assert find_changes(db_session, read_body=_read(tmp_path)) == []


def test_since_keeps_only_the_recent_change(db_session, tmp_path):
    site = _site(db_session)
    _fetch(db_session, tmp_path, site, V1, T0)
    _fetch(db_session, tmp_path, site, V2, T0 + timedelta(days=1))
    _fetch(db_session, tmp_path, site, V3, T0 + timedelta(days=9))
    changes = find_changes(db_session, since=T0 + timedelta(days=8))
    assert [c["new"]["fetched_at"] for c in changes] == ["2026-12-07T04:00:00+00:00"]
    assert changes[0]["review"] == "body missing"  # no reader given
