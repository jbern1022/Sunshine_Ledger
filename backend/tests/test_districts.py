from datetime import date

from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import select

from app.api.districts import metric_reliability
from app.districts.service import ensure_current_plan, members, plan_on, sponsored_bill_ids, sync_districts
from app.models import Bill, DemographicOverlay, District, Entity, OfficeTenure, Relationship, SpatialContext, Tag


def _person(db, name, district=None):
    e = Entity(entity_type="person", name=name, jurisdiction_level="state", jurisdiction_name="FL", external_ids={},
               attributes={"district": district} if district else {})
    db.add(e)
    db.flush()
    return e


def _bill(db, number, introduced):
    e = Entity(entity_type="bill", name=f"Bill {number}", jurisdiction_level="state", jurisdiction_name="FL", external_ids={}, attributes={})
    db.add(e)
    db.flush()
    db.add(Bill(entity_id=e.id, bill_number=number, session="2025", status="Introduced", introduced_date=introduced, source_system="legiscan"))
    db.flush()
    return e


def _sponsor(db, person, bill, kind="sponsor"):
    db.add(Relationship(from_entity_id=person.id, to_entity_id=bill.id, relationship_type=kind, attributes={}))
    db.flush()


def _tenure(db, person, office, district, start, end=None):
    t = OfficeTenure(person_entity_id=person.id, office_type=office, district=district, start_date=start, end_date=end,
                     source="test", attributes={})
    db.add(t)
    db.flush()
    return t


def _ids(db, code):
    return set(db.execute(sponsored_bill_ids(code)).scalars())


def test_a_member_who_changed_districts_is_counted_where_they_sat_when_they_filed(db_session):
    pat = _person(db_session, "Pat Doe", "SD-003")  # current record says Senate 3
    _tenure(db_session, pat, "fl_house", 5, date(2022, 11, 22), date(2024, 11, 5))
    _tenure(db_session, pat, "fl_senate", 3, date(2024, 11, 5))
    old = _bill(db_session, "HB 1", date(2023, 3, 1))
    new = _bill(db_session, "SB 9", date(2025, 3, 1))
    _sponsor(db_session, pat, old)
    _sponsor(db_session, pat, new, "co_sponsor")
    assert _ids(db_session, "HD-005") == {old.id}
    assert _ids(db_session, "SD-003") == {new.id}
    assert _ids(db_session, "HD-006") == set()


def test_a_person_with_no_tenure_falls_back_to_their_current_district(db_session):
    lee = _person(db_session, "Lee Roe", "HD-010")
    b = _bill(db_session, "HB 2", date(2025, 2, 1))
    _sponsor(db_session, lee, b)
    assert _ids(db_session, "HD-010") == {b.id}
    # but once tenures exist for them, the current record no longer decides
    _tenure(db_session, lee, "fl_house", 11, date(2022, 11, 22))
    assert _ids(db_session, "HD-010") == set()
    assert _ids(db_session, "HD-011") == {b.id}


def test_members_lists_past_and_current_holders_and_roster_fallback(db_session):
    plan = ensure_current_plan(db_session)
    d = District(map_plan_id=plan.id, chamber="house", number=5, code="HD-005")
    db_session.add(d)
    old = _person(db_session, "Old Member", "HD-099")
    _tenure(db_session, old, "fl_house", 5, date(2018, 11, 20), date(2022, 11, 22))
    cur = _person(db_session, "Current Member", "HD-005")
    _tenure(db_session, cur, "fl_house", 5, date(2022, 11, 22))
    rosterish = _person(db_session, "Roster Only", "HD-005")
    got = {m["name"]: m for m in members(db_session, d)}
    assert got["Old Member"]["current"] is False and got["Old Member"]["basis"] == "tenure"
    assert got["Current Member"]["current"] is True
    assert got["Roster Only"]["basis"] == "current_roster" and got["Roster Only"]["person_entity_id"] == rosterish.id


def test_sync_districts_builds_from_boundaries_and_is_idempotent(db_session):
    poly = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])])
    for name in ("HD-101", "SD-024"):
        db_session.add(SpatialContext(scope_type="district", scope_name=name, geom=from_shape(poly, srid=4326)))
    db_session.flush()
    first = sync_districts(db_session)
    assert first["created"] == 2 and first["linked"] == 2
    assert sync_districts(db_session) == {"created": 0, "linked": 0, "skipped": 0}
    assert {d.code for d in db_session.execute(select(District)).scalars()} == {"HD-101", "SD-024"}


def test_map_plan_is_chosen_by_date(db_session):
    ensure_current_plan(db_session)
    assert plan_on(db_session, date(2024, 6, 1)).key == "fl-state-2022"
    assert plan_on(db_session, date(2020, 6, 1)) is None


def test_reliability_flags_and_suppresses_by_margin_of_error():
    assert metric_reliability(1000, 50)["reliability"] == "ok"
    assert metric_reliability(100, 40)["reliability"] == "ok"            # CV 24%
    assert metric_reliability(100, 60)["reliability"] == "high_moe"      # CV 36%
    cut = metric_reliability(100, 120)                                    # as large as the estimate
    assert cut["suppressed"] and cut["estimate"] is None and cut["margin_of_error"] == 120
    assert metric_reliability(5, None)["reliability"] == "unknown"        # BLS-style: no MOE published


def test_district_page_shows_residents_label_vintage_and_moe(client, db_session):
    plan = ensure_current_plan(db_session)
    db_session.add(District(map_plan_id=plan.id, chamber="house", number=101, code="HD-101"))
    db_session.add(Tag(slug="housing", label="Housing"))
    db_session.add(DemographicOverlay(
        geography_type="district", geography_id="HD-101", badge_slug="housing", source="acs", as_of="2024",
        metrics=[{"label": "Renter households", "estimate": 40000, "margin_of_error": 1200, "unit": "households"},
                 {"label": "Tiny group", "estimate": 100, "margin_of_error": 150, "unit": "people"}],
    ))
    pat = _person(db_session, "Pat Doe", "HD-101")
    b = _bill(db_session, "HB 7", date(2025, 4, 1))
    _sponsor(db_session, pat, b)
    body = client.get("/districts/HD-101").json()
    assert body["code"] == "HD-101" and body["map_plan"]["key"] == "fl-state-2022"
    assert body["census_profile"]["population"] == "residents"
    assert "not voters or the electorate" in body["census_profile"]["label"]
    group = body["census_profile"]["profile"][0]
    assert group["vintage"] == "2024" and group["badge_label"] == "Housing"
    renter, tiny = group["metrics"]
    assert renter["margin_of_error"] == 1200 and renter["reliability"] == "ok"
    assert tiny["suppressed"] is True and tiny["estimate"] is None
    assert [m["name"] for m in body["members"]] == ["Pat Doe"]
    assert body["sponsored_bills"]["total"] == 1 and body["sponsored_bills"]["items"][0]["bill_number"] == "HB 7"
    assert not any(k in body for k in ("score", "alignment", "electorate"))


def test_bad_or_unknown_district_codes_404(client, db_session):
    ensure_current_plan(db_session)
    assert client.get("/districts/HD-1").status_code == 404
    assert client.get("/districts/ZZ-001").status_code == 404
    assert client.get("/districts/HD-999").status_code == 404


def test_bill_and_people_lists_filter_by_district(client, db_session):
    pat = _person(db_session, "Pat Doe", "SD-003")
    _tenure(db_session, pat, "fl_house", 5, date(2022, 11, 22), date(2024, 11, 5))
    _tenure(db_session, pat, "fl_senate", 3, date(2024, 11, 5))
    old = _bill(db_session, "HB 1", date(2023, 3, 1))
    new = _bill(db_session, "SB 9", date(2025, 3, 1))
    _sponsor(db_session, pat, old)
    _sponsor(db_session, pat, new)
    hd = client.get("/bills?district=HD-005").json()
    sd = client.get("/bills?district=SD-003").json()
    assert [b["bill_number"] for b in hd["items"]] == ["HB 1"]
    assert [b["bill_number"] for b in sd["items"]] == ["SB 9"]
    assert client.get("/bills?district=nonsense").status_code == 422
    assert [p["name"] for p in client.get("/people?district=HD-005").json()["items"]] == ["Pat Doe"]
    assert client.get("/people?district=HD-006").json()["items"] == []


# --- congressional districts ------------------------------------------------


def test_congressional_boundaries_load_as_their_own_scope(db_session, tmp_path):
    import shapefile

    from app.pipeline.load_boundaries import CONGRESSIONAL_SCOPE, load_tiger_congressional

    path = tmp_path / "cd"
    with shapefile.Writer(str(path)) as w:
        w.field("STATEFP", "C", size=2)
        w.field("CD119FP", "C", size=2)
        w.poly([[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]])
        w.record("12", "07")
        w.poly([[[2, 2], [2, 3], [3, 3], [3, 2], [2, 2]]])
        w.record("12", "ZZ")  # undistricted: skipped
        w.poly([[[4, 4], [4, 5], [5, 5], [5, 4], [4, 4]]])
        w.record("13", "01")  # Georgia: skipped
    assert load_tiger_congressional(db_session, path.with_suffix(".shp")) == 1
    ctx = db_session.execute(select(SpatialContext)).scalar_one()
    assert (ctx.scope_type, ctx.scope_name) == (CONGRESSIONAL_SCOPE, "CD-007")
    assert load_tiger_congressional(db_session, path.with_suffix(".shp")) == 1  # replaces, no duplicates
    assert len(db_session.execute(select(SpatialContext)).scalars().all()) == 1


def test_sync_builds_both_plans_without_mixing_scopes(db_session):
    poly = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])])
    db_session.add(SpatialContext(scope_type="district", scope_name="HD-101", geom=from_shape(poly, srid=4326)))
    db_session.add(SpatialContext(scope_type="congress_district", scope_name="CD-012", geom=from_shape(poly, srid=4326)))
    db_session.flush()
    assert sync_districts(db_session)["created"] == 2
    rows = {d.code: d for d in db_session.execute(select(District)).scalars()}
    assert rows["CD-012"].chamber == "us_house" and rows["HD-101"].chamber == "house"
    assert rows["CD-012"].map_plan_id != rows["HD-101"].map_plan_id
    assert plan_on(db_session, date(2025, 1, 1), "congress").key == "fl-congress-2022"
    assert plan_on(db_session, date(2025, 1, 1)).key == "fl-state-2022"  # two plans in force, each found by scope


def test_congressional_page_lists_members_from_tenures_and_labels_residents(client, db_session):
    from app.federal.roster import import_roster
    import json
    from pathlib import Path

    sample = json.loads((Path(__file__).parent / "fixtures" / "congress_legislators_sample.json").read_text())
    import_roster(db_session, sample, today=date(2026, 11, 10))
    poly = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])])
    db_session.add(SpatialContext(scope_type="congress_district", scope_name="CD-012", geom=from_shape(poly, srid=4326)))
    db_session.add(Tag(slug="housing", label="Housing"))
    db_session.add(DemographicOverlay(
        geography_type="district", geography_id="CD-012", badge_slug="housing", source="acs", as_of="2024",
        metrics=[{"label": "Renter households", "estimate": 90000, "margin_of_error": 2000, "unit": "households"}],
    ))
    db_session.flush()
    sync_districts(db_session)
    body = client.get("/districts/CD-012").json()
    assert body["chamber"] == "us_house" and body["map_plan"]["key"] == "fl-congress-2022"
    assert any(m["name"] == "Gus M. Bilirakis" and m["basis"] == "tenure" and m["current"] for m in body["members"])
    # his earlier tenure in District 9 is not listed on CD-012
    assert sum(1 for m in body["members"] if m["name"] == "Gus M. Bilirakis") >= 1
    assert "not voters or the electorate" in body["census_profile"]["label"]
    assert body["census_profile"]["profile"][0]["metrics"][0]["margin_of_error"] == 2000
    listing = client.get("/districts").json()
    assert listing["congressional_map_plan"]["key"] == "fl-congress-2022"
    assert [i["code"] for i in client.get("/districts?chamber=us_house").json()["items"]] == ["CD-012"]
    assert [p["name"] for p in client.get("/people?district=CD-012").json()["items"]] in ([], ["Gus M. Bilirakis"])


def test_acs_congressional_overlays_use_cd_prefix_and_leave_state_loader_alone(db_session):
    from app.pipeline.demographic_overlay import load_acs_district_overlays

    class Fake:
        def __init__(self):
            self.calls = []

        def get_by_district(self, variables, *, chamber):
            self.calls.append(chamber)
            return {"12": {v: "100" for v in variables}}

    f = Fake()
    assert load_acs_district_overlays(db_session, badge_slug="housing", client=f, prefixes=("CD",)) == 1
    assert f.calls == ["CD"]
    assert db_session.execute(select(DemographicOverlay)).scalar_one().geography_id == "CD-012"


def test_point_lookup_returns_every_district_that_covers_it(client, db_session):
    def square(x0, y0, x1, y1):
        return from_shape(MultiPolygon([Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])]), srid=4326)

    # one state House district, one state Senate, one congressional, one elsewhere
    for scope, name, geom in (
        ("district", "HD-101", square(-81, 28, -80, 29)),
        ("district", "SD-024", square(-82, 27, -79.9, 30)),
        ("congress_district", "CD-012", square(-81.5, 27.5, -79.95, 29.5)),
        ("district", "HD-102", square(-86, 30, -85, 31)),
    ):
        db_session.add(SpatialContext(scope_type=scope, scope_name=name, geom=geom))
    db_session.flush()
    sync_districts(db_session)
    got = client.get("/districts/at?lat=28.5&lon=-80.5").json()["districts"]
    assert {d["code"] for d in got} == {"HD-101", "SD-024", "CD-012"}
    assert client.get("/districts/at?lat=30.5&lon=-85.5").json()["districts"][0]["code"] == "HD-102"
    assert client.get("/districts/at?lat=26.0&lon=-85.0").json()["districts"] == []
    assert client.get("/districts/at?lat=40.0&lon=-80.5").status_code == 422  # outside Florida
