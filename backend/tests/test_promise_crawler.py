from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app.models import ElectionWinner, OfficialSite, SiteSnapshot
from app.promises.crawler import Crawler, classify_page, pick_links
from app.promises.sites import SiteError, add_site, import_sites_csv, is_social, normalize_url
from app.promises.snapshot_text import snapshot_text

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
HOME = b"""<html><body><nav><a href="/issues">Issues</a></nav>
<a href="/issues">Our Priorities</a><a href="/about-jane">About</a><a href="/news/one">News</a>
<a href="https://facebook.com/jane">Facebook</a><a href="https://other.example/issues">Elsewhere</a>
<a href="/photo.jpg">pic</a><a href="/donate">Donate</a><p>I will cut property taxes.</p></body></html>"""


def _winner(db, district=1):
    w = ElectionWinner(cycle=2026, chamber="house", district=district, name="Jane Smith",
                       result_status="unofficial", source_url="u", source_retrieved_at=NOW, change_log=[])
    db.add(w)
    db.flush()
    return w


def _site(db, w, url="https://jane.example/"):
    return add_site(db, w, url, kind="campaign", discovered_via="manual", now=NOW)


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def now(self):
        return self.t


def _crawler(db, tmp_path, handler, **kw):
    clock = Clock()
    c = Crawler(
        db, client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
        pace=kw.pop("pace", 60.0), storage_dir=str(tmp_path), sleep=clock.sleep, clock=clock.now,
        now=lambda: NOW, **kw,
    )
    return c, clock


def html(body=HOME):
    return httpx.Response(200, content=body, headers={"content-type": "text/html; charset=utf-8"})


def site_handler(request):
    p = request.url.path
    if p == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /donate\n")
    return html()


def test_classify_and_pick_links():
    assert classify_page("https://x/issues") == "issues"
    assert classify_page("https://x/a", "About Jane") == "about"
    links = pick_links("https://jane.example/", HOME)
    urls = [u for _, u in links]
    assert urls == ["https://jane.example/issues", "https://jane.example/about-jane", "https://jane.example/news/one"]


def test_social_urls_are_never_added(db_session):
    w = _winner(db_session)
    assert is_social("https://www.facebook.com/jane") and is_social("https://m.youtube.com/x")
    assert add_site(db_session, w, "https://facebook.com/jane", kind="campaign", discovered_via="manual") is None
    with pytest.raises(SiteError):
        normalize_url("ftp://x/")


def test_import_sites_csv(db_session):
    _winner(db_session, 7)
    out = import_sites_csv(db_session, "chamber,district,url,kind\nhouse,7,https://a.example/,campaign\nhouse,7,https://a.example/,campaign\nhouse,99,https://b.example/,campaign\n", cycle=2026)
    assert out == {"added": 1, "skipped": 1, "unknown_seat": 1}


def test_crawl_snapshots_home_and_linked_pages(db_session, tmp_path):
    site = _site(db_session, _winner(db_session))
    c, clock = _crawler(db_session, tmp_path, site_handler)
    out = c.run([site])
    assert out["snapshots"] == 4 and out["unavailable"] == 0
    snaps = db_session.execute(select(SiteSnapshot)).scalars().all()
    assert {s.page_kind for s in snaps} == {"home", "issues", "about", "news"}
    assert site.status == "live"
    s = snaps[0]
    assert (tmp_path / s.storage_path).read_bytes() == HOME and len(s.content_hash) == 64
    # robots.txt once, then 4 pages, each at least `pace` apart
    assert c.requests == 5 and all(x >= 59 for x in clock.sleeps)


def test_resume_skips_what_is_done(db_session, tmp_path):
    site = _site(db_session, _winner(db_session))
    c, _ = _crawler(db_session, tmp_path, site_handler)
    c.run([site])
    c2, _ = _crawler(db_session, tmp_path, site_handler)
    c2.run([site])
    assert c2.requests == 0  # nothing to refetch, robots not even needed
    assert db_session.execute(select(SiteSnapshot)).scalars().all().__len__() == 4


def test_cap_stops_the_run_and_a_rerun_finishes(db_session, tmp_path):
    site = _site(db_session, _winner(db_session))
    c, _ = _crawler(db_session, tmp_path, site_handler, max_requests=3)
    out = c.run([site])
    assert out["capped"] and c.requests == 3
    first = db_session.execute(select(SiteSnapshot)).scalars().all().__len__()
    c2, _ = _crawler(db_session, tmp_path, site_handler, max_requests=50)
    c2.run([site])
    assert db_session.execute(select(SiteSnapshot)).scalars().all().__len__() == 4 > first


def test_robots_disallow_is_recorded_not_bypassed(db_session, tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        raise AssertionError("fetched a disallowed page")

    site = _site(db_session, _winner(db_session))
    c, _ = _crawler(db_session, tmp_path, handler)
    out = c.run([site])
    assert out["blocked"] == 1 and site.status == "blocked"
    assert db_session.execute(select(SiteSnapshot)).scalar_one().status == "blocked_by_robots"


def test_crawl_delay_in_robots_raises_the_pace(db_session, tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 120\n")
        return html()

    site = _site(db_session, _winner(db_session))
    c, clock = _crawler(db_session, tmp_path, handler, pace=10.0)
    c.run([site])
    assert max(clock.sleeps) >= 119


def test_cross_host_redirect_is_refused(db_session, tmp_path):
    def handler(request):
        if request.url.host == "jane.example" and request.url.path != "/robots.txt":
            return httpx.Response(302, headers={"location": "https://elsewhere.example/"})
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return html(b"<p>other</p>")

    site = _site(db_session, _winner(db_session))
    c, _ = _crawler(db_session, tmp_path, handler)
    c.run([site])
    s = db_session.execute(select(SiteSnapshot)).scalar_one()
    assert s.status == "refused" and "another host" in s.note


def test_offline_site_falls_back_to_the_internet_archive(db_session, tmp_path):
    def handler(request):
        if request.url.host == "jane.example":
            return httpx.Response(404) if request.url.path == "/robots.txt" else httpx.Response(503)
        if request.url.host == "archive.org":
            return httpx.Response(200, json={"archived_snapshots": {"closest": {
                "available": True, "timestamp": "20261105000000", "url": "http://web.archive.org/web/20261105000000/https://jane.example/"}}})
        if request.url.host == "web.archive.org":
            assert "20261105000000id_/https://jane.example/" in str(request.url)
            return html(b"<p>I will fix the roads.</p>")
        raise AssertionError(request.url)

    site = _site(db_session, _winner(db_session))
    c, _ = _crawler(db_session, tmp_path, handler)
    out = c.run([site])
    assert site.status == "offline" and site.archive_timestamp == "20261105000000"
    assert out["snapshots"] == 1 and out["unavailable"] == 1
    archived = [s for s in db_session.execute(select(SiteSnapshot)).scalars() if s.from_archive_timestamp]
    assert len(archived) == 1 and archived[0].status == "ok"


def test_unreadable_robots_means_no_crawl(db_session, tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(500)
        raise AssertionError("crawled without robots")

    site = _site(db_session, _winner(db_session))
    c, _ = _crawler(db_session, tmp_path, handler)
    c.run([site])
    assert db_session.execute(select(SiteSnapshot)).scalar_one().status == "unavailable"


def test_snapshot_text_is_stable_and_drops_chrome():
    body = b"<html><head><style>x{}</style></head><body><nav>Menu</nav><h1>Jane</h1><p>I will  cut\n taxes.</p><script>evil()</script></body></html>"
    assert snapshot_text(body) == "Jane\nI will cut taxes."
    assert snapshot_text(body) == snapshot_text(body)


def test_snapshot_text_keeps_a_sentence_whole_across_inline_tags():
    assert snapshot_text(b"<p>I will <b>cut</b> property\n taxes.</p><p>Next.</p>") == "I will cut property taxes.\nNext."


# --- Re-crawl schedule (2026-11-27): a site is fetched again once its last full
# crawl is older than `recrawl_after`, so same-URL changes are seen
# (app.promises.changes). Before this, a page that succeeded once was never
# fetched again.

from datetime import timedelta  # noqa: E402

from app.promises.crawler import RECRAWL_AFTER  # noqa: E402

ISSUES_V2 = b"<html><body><h1>Issues</h1><p>I will cut property taxes and fix the roads.</p></body></html>"


def _crawler_at(db, tmp_path, handler, when, **kw):
    clock = Clock()
    return Crawler(
        db, client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
        pace=60.0, storage_dir=str(tmp_path), sleep=clock.sleep, clock=clock.now, now=lambda: when, **kw,
    )


def _changed_issues(request):
    if request.url.path == "/issues":
        return html(ISSUES_V2)
    return site_handler(request)


def _snaps(db):
    return db.execute(select(SiteSnapshot)).scalars().all()


def test_default_recrawl_interval_is_a_week():
    assert RECRAWL_AFTER == timedelta(days=7)


def test_a_site_is_not_refetched_inside_the_interval(db_session, tmp_path):
    site = _site(db_session, _winner(db_session))
    _crawler_at(db_session, tmp_path, site_handler, NOW).run([site])
    c = _crawler_at(db_session, tmp_path, _changed_issues, NOW + timedelta(days=6))
    c.run([site])
    assert c.requests == 0 and len(_snaps(db_session)) == 4
    assert site.last_checked_at == NOW  # nothing was looked at again


def test_a_site_is_refetched_after_the_interval_and_only_changes_add_snapshots(db_session, tmp_path):
    site = _site(db_session, _winner(db_session))
    _crawler_at(db_session, tmp_path, site_handler, NOW).run([site])
    later = NOW + timedelta(days=8)
    c = _crawler_at(db_session, tmp_path, _changed_issues, later)
    c.run([site])
    assert c.requests == 5  # robots + the same 4 pages
    snaps = _snaps(db_session)
    assert len(snaps) == 5  # unchanged pages keep their row; /issues gets a new one
    issues = sorted((s for s in snaps if s.url.endswith("/issues")), key=lambda s: s.fetched_at)
    assert [s.fetched_at for s in issues] == [NOW, later]
    assert (tmp_path / issues[-1].storage_path).read_bytes() == ISSUES_V2
    assert site.last_checked_at == later


def test_a_recrawl_cut_off_by_the_cap_is_still_due_next_run(db_session, tmp_path):
    site = _site(db_session, _winner(db_session))
    _crawler_at(db_session, tmp_path, site_handler, NOW).run([site])
    later = NOW + timedelta(days=8)
    c = _crawler_at(db_session, tmp_path, _changed_issues, later, max_requests=2)  # robots + home
    assert c.run([site])["capped"]
    assert site.last_checked_at == NOW  # not a complete crawl
    c2 = _crawler_at(db_session, tmp_path, _changed_issues, later + timedelta(hours=1))
    c2.run([site])
    assert c2.requests == 5 and site.last_checked_at == later + timedelta(hours=1)
    assert any(s.url.endswith("/issues") and s.fetched_at > NOW for s in _snaps(db_session))


def test_recrawl_interval_can_be_set(db_session, tmp_path):
    site = _site(db_session, _winner(db_session))
    _crawler_at(db_session, tmp_path, site_handler, NOW).run([site])
    c = _crawler_at(db_session, tmp_path, site_handler, NOW + timedelta(days=2), recrawl_after=timedelta(days=1))
    c.run([site])
    assert c.requests == 5
