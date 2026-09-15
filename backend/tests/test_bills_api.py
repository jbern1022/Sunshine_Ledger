import uuid
from datetime import date

from app.models import BillTag, DemographicOverlay, Entity, Event, Relationship, Tag
from app.pipeline.topic_tagging import assign_tags_for_bill, set_bill_tag_active


def test_list_bills_empty(client):
    resp = client.get("/bills")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_bills_returns_created_bill(client, bill_factory):
    entity = bill_factory()

    resp = client.get("/bills")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["bill_number"] == "HB 123"
    assert body["items"][0]["entity_id"] == str(entity.id)


def test_list_bills_filters_by_status(client, bill_factory):
    bill_factory(bill_number="HB 1", status="Introduced")
    bill_factory(bill_number="HB 2", status="Passed")

    resp = client.get("/bills", params={"status": "Passed"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["bill_number"] == "HB 2"


def test_list_bills_search_matches_bill_number(client, bill_factory):
    bill_factory(bill_number="HB 456", name="Unrelated title")

    resp = client.get("/bills", params={"q": "HB 456"})
    body = resp.json()
    assert body["total"] == 1


def test_list_bills_filters_by_geo_scope_name(client, bill_factory):
    bill_factory(bill_number="HB 1", geo_scope_names=["Miami-Dade County"])
    bill_factory(bill_number="HB 2", geo_scope_names=["Duval County"])

    resp = client.get("/bills", params={"geo_scope_name": "Miami-Dade County"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["bill_number"] == "HB 1"


def _add_sponsor(db, bill_entity, *, name: str, rel_type: str = "sponsor"):
    person = Entity(
        entity_type="person",
        name=name,
        jurisdiction_level="state",
        jurisdiction_name="FL",
        external_ids={"legiscan_people_id": name},
        attributes={},
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


def test_list_bills_filters_by_sponsor_entity_id(client, db_session, bill_factory):
    sponsored = bill_factory(bill_number="HB 1")
    bill_factory(bill_number="HB 2")
    sponsor = _add_sponsor(db_session, sponsored, name="Jim Mooney")

    resp = client.get("/bills", params={"sponsor_entity_id": str(sponsor.id)})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["bill_number"] == "HB 1"


def test_list_bills_sponsor_filter_includes_co_sponsors(client, db_session, bill_factory):
    bill = bill_factory(bill_number="HB 1")
    co_sponsor = _add_sponsor(db_session, bill, name="Co Sponsor", rel_type="co_sponsor")

    resp = client.get("/bills", params={"sponsor_entity_id": str(co_sponsor.id)})
    body = resp.json()
    assert body["total"] == 1


def test_list_bills_sponsor_filter_no_matches(client, bill_factory):
    bill_factory(bill_number="HB 1")

    resp = client.get("/bills", params={"sponsor_entity_id": str(uuid.uuid4())})
    body = resp.json()
    assert body["total"] == 0


def test_get_bill_detail(client, bill_factory):
    entity = bill_factory()

    resp = client.get(f"/bills/{entity.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bill_number"] == "HB 123"
    assert body["claims"] == []
    assert body["news"] == []
    assert body["votes"] == []


def test_get_bill_not_found(client):
    resp = client.get(f"/bills/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_bill_detail_includes_a_roll_call_and_its_individual_votes(client, bill_factory, db_session):
    entity = bill_factory()
    person = Entity(
        entity_type="person",
        name="Jane Smith",
        jurisdiction_level="state",
        jurisdiction_name="FL",
        external_ids={"legiscan_people_id": "19426"},
        attributes={},
    )
    db_session.add(person)
    db_session.flush()

    vote_event = Event(
        entity_id=entity.id,
        event_type="vote",
        event_date=date(2026, 2, 25),
        title="House: Third Reading RCS#549",
        attributes={
            "roll_call_id": "1644238",
            "chamber": "H",
            "yea": 82,
            "nay": 30,
            "nv": 5,
            "absent": 0,
            "total": 117,
            "passed": True,
        },
    )
    db_session.add(vote_event)
    db_session.add(
        Relationship(
            from_entity_id=person.id,
            to_entity_id=entity.id,
            relationship_type="voted",
            attributes={"roll_call_id": "1644238", "vote": "Yea"},
        )
    )
    db_session.commit()

    resp = client.get(f"/bills/{entity.id}")
    assert resp.status_code == 200
    votes = resp.json()["votes"]

    assert len(votes) == 1
    roll_call = votes[0]
    assert roll_call["description"] == "House: Third Reading RCS#549"
    assert roll_call["yea"] == 82
    assert roll_call["passed"] is True
    assert roll_call["votes"] == [
        {"person_entity_id": str(person.id), "person_name": "Jane Smith", "vote": "Yea"}
    ]


# --- status filter options ------------------------------------------------


def test_statuses_endpoint_is_empty_without_bills(client):
    assert client.get("/bills/statuses").json() == []


def test_statuses_returns_counts(client, bill_factory):
    bill_factory(bill_number="HB 1", status="Introduced")
    bill_factory(bill_number="HB 2", status="Introduced")
    bill_factory(bill_number="HB 3", status="Passed")

    body = client.get("/bills/statuses").json()
    assert {s["status"]: s["count"] for s in body} == {"Introduced": 2, "Passed": 1}


def test_statuses_ordered_by_count_descending(client, bill_factory):
    """Common statuses first so a dropdown isn't led by one-off municipal
    vocabulary."""
    bill_factory(bill_number="HB 1", status="Rare Status")
    for i in range(3):
        bill_factory(bill_number=f"HB 1{i}", status="Introduced")

    assert [s["status"] for s in client.get("/bills/statuses").json()] == ["Introduced", "Rare Status"]


def test_statuses_scoped_by_jurisdiction(client, db_session, bill_factory):
    a = bill_factory(bill_number="HB 1", status="Introduced")
    b = bill_factory(bill_number="ORD 1", status="Enacted")
    b.jurisdiction_name = "Jacksonville"
    db_session.commit()

    body = client.get("/bills/statuses", params={"jurisdiction_name": "Jacksonville"}).json()
    assert [s["status"] for s in body] == ["Enacted"]
    assert a.jurisdiction_name == "FL"


def test_statuses_route_is_not_shadowed_by_the_bill_detail_route(client, bill_factory):
    """FastAPI matches in definition order, so /bills/{entity_id} declared
    first would swallow this path and fail parsing "statuses" as a UUID."""
    bill_factory()
    assert client.get("/bills/statuses").status_code == 200


# --- bill topic tagging ----------------------------------------------------


def test_bill_list_includes_active_tags(client, db_session, bill_factory):
    entity = bill_factory()
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing"])

    body = client.get("/bills").json()
    assert body["items"][0]["tags"] == [
        {
            "bill_tag_id": body["items"][0]["tags"][0]["bill_tag_id"],
            "slug": "housing",
            "label": "Housing",
            "tag_source": "ollama",
            "active": True,
        }
    ]


def test_bill_list_excludes_hidden_tags(client, db_session, bill_factory):
    entity = bill_factory()
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    created = assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing"])
    set_bill_tag_active(db_session, created[0].id, active=False)

    body = client.get("/bills").json()
    assert body["items"][0]["tags"] == []


def test_bill_detail_includes_tags(client, db_session, bill_factory):
    entity = bill_factory()
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing"])

    body = client.get(f"/bills/{entity.id}").json()
    assert len(body["tags"]) == 1
    assert body["tags"][0]["slug"] == "housing"


def test_bill_list_filters_by_tag(client, db_session, bill_factory):
    a = bill_factory(bill_number="HB 1")
    bill_factory(bill_number="HB 2")
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    assign_tags_for_bill(db_session, a.id, ollama_tag_slugs=["housing"])

    body = client.get("/bills", params={"tag": "housing"}).json()
    assert body["total"] == 1
    assert body["items"][0]["bill_number"] == "HB 1"


def test_bill_list_tag_filter_excludes_hidden(client, db_session, bill_factory):
    a = bill_factory(bill_number="HB 1")
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    created = assign_tags_for_bill(db_session, a.id, ollama_tag_slugs=["housing"])
    set_bill_tag_active(db_session, created[0].id, active=False)

    body = client.get("/bills", params={"tag": "housing"}).json()
    assert body["total"] == 0


def test_list_tags_endpoint_returns_counts(client, db_session, bill_factory):
    a = bill_factory(bill_number="HB 1")
    b = bill_factory(bill_number="HB 2")
    housing = Tag(slug="housing", label="Housing", active=True)
    taxes = Tag(slug="taxes_budget", label="Taxes/Budget", active=True)
    db_session.add_all([housing, taxes])
    db_session.commit()
    assign_tags_for_bill(db_session, a.id, ollama_tag_slugs=["housing"])
    assign_tags_for_bill(db_session, b.id, ollama_tag_slugs=["housing", "taxes_budget"])

    body = client.get("/bills/tags").json()
    counts = {row["slug"]: row["count"] for row in body}
    assert counts == {"housing": 2, "taxes_budget": 1}


def test_list_tags_endpoint_excludes_inactive_tag_categories(client, db_session, bill_factory):
    a = bill_factory()
    tag = Tag(slug="housing", label="Housing", active=False)
    db_session.add(tag)
    db_session.commit()
    assign_tags_for_bill(db_session, a.id, ollama_tag_slugs=["housing"])

    assert client.get("/bills/tags").json() == []


def test_patch_bill_tag_requires_auth(client, db_session, bill_factory):
    entity = bill_factory()
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    created = assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing"])

    resp = client.patch(f"/bills/tags/{created[0].id}", json={"active": False})
    assert resp.status_code == 401


def test_patch_bill_tag_hides_badge(client, db_session, bill_factory):
    entity = bill_factory()
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    created = assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing"])

    resp = client.patch(
        f"/bills/tags/{created[0].id}", json={"active": False}, auth=("testadmin", "testpass")
    )
    assert resp.status_code == 200
    assert resp.json()["active"] is False

    events = db_session.query(Event).filter(Event.entity_id == entity.id, Event.event_type == "tag_hidden").all()
    assert len(events) == 1


def test_patch_bill_tag_not_found(client):
    resp = client.patch(f"/bills/tags/{uuid.uuid4()}", json={"active": False}, auth=("testadmin", "testpass"))
    assert resp.status_code == 404


# --- ACS/BLS demographic overlay -------------------------------------------


def test_bill_detail_includes_overlay_via_sponsors_district(client, db_session, bill_factory):
    """State bill: geography comes from the primary sponsor's district."""
    entity = bill_factory()
    sponsor = Entity(
        entity_type="person", name="Jane Smith", jurisdiction_level="state", jurisdiction_name="FL",
        external_ids={}, attributes={"district": "HD-101"},
    )
    db_session.add(sponsor)
    db_session.flush()
    db_session.add(Relationship(from_entity_id=sponsor.id, to_entity_id=entity.id, relationship_type="sponsor"))
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing"])
    db_session.add(
        DemographicOverlay(
            geography_type="district", geography_id="HD-101", badge_slug="housing", source="acs",
            metrics=[{"label": "Owner-occupied", "estimate": 38959.0, "margin_of_error": 1242.0, "unit": "housing units"}],
            as_of="2022",
        )
    )
    db_session.commit()

    body = client.get(f"/bills/{entity.id}").json()
    assert len(body["demographic_overlays"]) == 1
    overlay = body["demographic_overlays"][0]
    assert overlay["badge_slug"] == "housing"
    assert overlay["geography_type"] == "district"
    assert overlay["geography_id"] == "HD-101"
    assert overlay["metrics"][0]["margin_of_error"] == 1242.0


def test_bill_detail_includes_overlay_via_county_for_local_bill(client, db_session, bill_factory):
    entity = bill_factory(geo_scope_names=["Duval County"])
    entity.jurisdiction_level = "city"
    tag = Tag(slug="infrastructure_transportation", label="Infrastructure/Transportation", active=True)
    db_session.add(tag)
    db_session.commit()
    assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["infrastructure_transportation"])
    db_session.add(
        DemographicOverlay(
            geography_type="county", geography_id="Duval County", badge_slug="infrastructure_transportation",
            source="acs", metrics=[{"label": "Aggregate travel time", "estimate": 433097.0, "margin_of_error": 4310.0, "unit": "minutes"}],
            as_of="2022",
        )
    )
    db_session.commit()

    body = client.get(f"/bills/{entity.id}").json()
    assert len(body["demographic_overlays"]) == 1
    assert body["demographic_overlays"][0]["geography_type"] == "county"
    assert body["demographic_overlays"][0]["geography_id"] == "Duval County"


def test_bill_detail_overlay_empty_without_a_resolvable_sponsor(client, db_session, bill_factory):
    """State bill, no sponsor on file -- geography can't be resolved, so no
    overlay is shown. Never an error."""
    entity = bill_factory()
    tag = Tag(slug="housing", label="Housing", active=True)
    db_session.add(tag)
    db_session.commit()
    assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing"])
    db_session.add(
        DemographicOverlay(
            geography_type="district", geography_id="HD-101", badge_slug="housing", source="acs",
            metrics=[], as_of="2022",
        )
    )
    db_session.commit()

    body = client.get(f"/bills/{entity.id}").json()
    assert body["demographic_overlays"] == []


def test_bill_detail_overlay_empty_for_a_badge_with_no_table_mapping(client, db_session, bill_factory):
    """A tag whose badge has no ACS/BLS table (e.g. Governance) contributes
    no overlay -- degrades gracefully, not an error."""
    entity = bill_factory()
    sponsor = Entity(
        entity_type="person", name="Jane Smith", jurisdiction_level="state", jurisdiction_name="FL",
        external_ids={}, attributes={"district": "HD-101"},
    )
    db_session.add(sponsor)
    db_session.flush()
    db_session.add(Relationship(from_entity_id=sponsor.id, to_entity_id=entity.id, relationship_type="sponsor"))
    tag = Tag(slug="governance", label="Governance", active=True)
    db_session.add(tag)
    db_session.commit()
    assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["governance"])
    db_session.commit()

    body = client.get(f"/bills/{entity.id}").json()
    assert body["demographic_overlays"] == []


def test_bill_detail_overlay_empty_for_labor_employment_on_a_state_bill(client, db_session, bill_factory):
    """Deliberate, documented consequence of the BLS-is-county-only decision:
    Labor/Employment has no ACS table mapping (BLS-only), and BLS data is
    only ever stored at county granularity -- but a state bill's geography
    always resolves to its sponsor's DISTRICT, never a county. So a state
    bill tagged Labor/Employment can never match an overlay row, by design.
    This pins that as an intentional empty result, not a crash or a silent
    bug regression."""
    entity = bill_factory()
    sponsor = Entity(
        entity_type="person", name="Jane Smith", jurisdiction_level="state", jurisdiction_name="FL",
        external_ids={}, attributes={"district": "HD-101"},
    )
    db_session.add(sponsor)
    db_session.flush()
    db_session.add(Relationship(from_entity_id=sponsor.id, to_entity_id=entity.id, relationship_type="sponsor"))
    tag = Tag(slug="labor_employment", label="Labor/Employment", active=True)
    db_session.add(tag)
    db_session.commit()
    assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["labor_employment"])
    # Even if a labor_employment row somehow existed at county grain, it
    # still shouldn't match -- only a "district" row would match this bill.
    db_session.add(
        DemographicOverlay(
            geography_type="county", geography_id="Miami-Dade County", badge_slug="labor_employment",
            source="bls", metrics=[{"label": "Unemployment rate", "estimate": 2.5, "margin_of_error": None, "unit": "percent"}],
            as_of="2024-12",
        )
    )
    db_session.commit()

    body = client.get(f"/bills/{entity.id}").json()
    assert body["demographic_overlays"] == []


def test_bill_detail_overlay_renders_multiple_badges_without_breaking(client, db_session, bill_factory):
    """Multi-tag bill: every applicable overlay shows, per the Roadmap
    decision (no priority pick)."""
    entity = bill_factory()
    sponsor = Entity(
        entity_type="person", name="Jane Smith", jurisdiction_level="state", jurisdiction_name="FL",
        external_ids={}, attributes={"district": "HD-101"},
    )
    db_session.add(sponsor)
    db_session.flush()
    db_session.add(Relationship(from_entity_id=sponsor.id, to_entity_id=entity.id, relationship_type="sponsor"))
    housing = Tag(slug="housing", label="Housing", active=True)
    infra = Tag(slug="infrastructure_transportation", label="Infrastructure/Transportation", active=True)
    db_session.add_all([housing, infra])
    db_session.commit()
    assign_tags_for_bill(db_session, entity.id, ollama_tag_slugs=["housing", "infrastructure_transportation"])
    db_session.add_all([
        DemographicOverlay(geography_type="district", geography_id="HD-101", badge_slug="housing", source="acs", metrics=[], as_of="2022"),
        DemographicOverlay(geography_type="district", geography_id="HD-101", badge_slug="infrastructure_transportation", source="acs", metrics=[], as_of="2022"),
    ])
    db_session.commit()

    body = client.get(f"/bills/{entity.id}").json()
    assert {o["badge_slug"] for o in body["demographic_overlays"]} == {"housing", "infrastructure_transportation"}
