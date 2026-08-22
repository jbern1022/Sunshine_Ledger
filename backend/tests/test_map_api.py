"""Map endpoint tests.

The district endpoint is the interesting one: it joins sponsors to polygons
through `Entity.attributes["district"]`, so these cover both the join itself
and the framing guarantees (sponsorship counts, not impact counts).
"""

from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, Polygon

from app.models import Entity, Relationship, SpatialContext


def _square(x: float, y: float) -> MultiPolygon:
    return MultiPolygon([Polygon([(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)])])


def _add_district(db, scope_name: str, *, x: float = 0.0):
    db.add(
        SpatialContext(
            scope_type="district",
            scope_name=scope_name,
            geom_source="test fixture",
            geom=from_shape(_square(x, 0.0), srid=4326),
        )
    )
    db.commit()


def _add_sponsor(db, bill_entity, *, name: str, district: str | None, rel_type: str = "sponsor"):
    person = Entity(
        entity_type="person",
        name=name,
        jurisdiction_level="state",
        jurisdiction_name="FL",
        external_ids={"legiscan_people_id": name},
        attributes={"district": district} if district else {},
    )
    db.add(person)
    db.flush()
    db.add(
        Relationship(
            from_entity_id=person.id,
            to_entity_id=bill_entity.id,
            relationship_type=rel_type,
        )
    )
    db.commit()
    return person


def test_districts_empty(client):
    resp = client.get("/map/districts")
    assert resp.status_code == 200
    assert resp.json() == {"type": "FeatureCollection", "features": []}


def test_districts_counts_sponsored_bills(client, db_session, bill_factory):
    _add_district(db_session, "HD-120")
    bill = bill_factory(bill_number="HB 1")
    _add_sponsor(db_session, bill, name="Jim Mooney", district="HD-120")

    feature = client.get("/map/districts").json()["features"][0]
    assert feature["properties"]["scope_name"] == "HD-120"
    assert feature["properties"]["bill_count"] == 1
    assert feature["properties"]["chamber"] == "State House"
    assert feature["properties"]["legislators"] == ["Jim Mooney"]


def test_districts_label_senate_chamber(client, db_session):
    _add_district(db_session, "SD-024")
    feature = client.get("/map/districts").json()["features"][0]
    assert feature["properties"]["chamber"] == "State Senate"
    assert feature["properties"]["bill_count"] == 0


def test_districts_include_zero_activity_districts(client, db_session, bill_factory):
    """A district with no sponsored bills must still render (shaded empty),
    otherwise the map would show holes rather than inactive districts."""
    _add_district(db_session, "HD-001", x=0.0)
    _add_district(db_session, "HD-002", x=5.0)
    bill = bill_factory(bill_number="HB 1")
    _add_sponsor(db_session, bill, name="Rep One", district="HD-001")

    by_name = {f["properties"]["scope_name"]: f["properties"]["bill_count"] for f in client.get("/map/districts").json()["features"]}
    assert by_name == {"HD-001": 1, "HD-002": 0}


def test_districts_ignores_sponsors_without_district(client, db_session, bill_factory):
    """City-level sponsors (Legistar/iQM2) have no district attribute and must
    not leak into state district counts."""
    _add_district(db_session, "HD-001")
    bill = bill_factory(bill_number="HB 1")
    _add_sponsor(db_session, bill, name="City Commissioner", district=None)

    feature = client.get("/map/districts").json()["features"][0]
    assert feature["properties"]["bill_count"] == 0


def test_districts_counts_cosponsors_without_double_counting(client, db_session, bill_factory):
    """Same legislator listed as both sponsor and co-sponsor on one bill
    counts once, not twice."""
    _add_district(db_session, "HD-050")
    bill = bill_factory(bill_number="HB 7")
    person = _add_sponsor(db_session, bill, name="Dual Role", district="HD-050", rel_type="sponsor")
    db_session.add(
        Relationship(
            from_entity_id=person.id,
            to_entity_id=bill.id,
            relationship_type="co_sponsor",
        )
    )
    db_session.commit()

    feature = client.get("/map/districts").json()["features"][0]
    assert feature["properties"]["bill_count"] == 1


def test_counties_endpoint_excludes_districts(client, db_session):
    """The impact map must never pick up district polygons -- they measure a
    different thing and would silently corrupt the county shading."""
    _add_district(db_session, "HD-001")
    assert client.get("/map/counties").json()["features"] == []
