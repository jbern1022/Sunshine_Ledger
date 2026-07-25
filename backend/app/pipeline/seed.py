"""Seed sample data so the app is fully browsable without live LegiScan/
Legistar/Ollama access — useful for local dev and for demoing the frontend.

All bill numbers, sponsor names, and summary text below are SAMPLE/DEMO
content, not real Florida legislation. Swap in real data via
`legiscan.ingest_state_bills` / `legistar.ingest_local_bills` /
`summarize.summarize_and_store` for production use.

Usage:
    python -m app.pipeline.seed
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.db import SessionLocal
from app.models import Bill, Claim, ClaimSource, Entity, Relationship, Source
from app.pipeline.load_boundaries import load_sample_boundaries

NOW = datetime.now(timezone.utc)

SAMPLE_BILLS = [
    {
        "bill_number": "SB 100 (DEMO)",
        "title": "Residential Water Heater Efficiency Standards",
        "session": "2026 Regular Session",
        "chamber": "Senate",
        "status": "In Committee",
        "jurisdiction_level": "state",
        "jurisdiction_name": "FL",
        "geo_scope_type": "statewide",
        "geo_scope_names": ["FL"],
        "introduced_date": date(2026, 1, 12),
        "last_action_date": date(2026, 2, 3),
        "last_action": "Referred to Regulated Industries Committee",
        "source_url": "https://www.flsenate.gov/Session/Bill/2026/0100",
        "source_system": "legiscan",
        "sponsor": "Sen. A. Delgado",
        "what_it_does": "This bill sets a minimum energy-efficiency rating for new residential water heaters sold in Florida, matching the current federal Department of Energy standard. Water heaters already installed before the rule takes effect can stay in use until they're replaced.",
        "who_it_affects": "Plumbing contractors and water heater manufacturers/retailers doing business in Florida, and homeowners who buy a new water heater after the effective date.",
    },
    {
        "bill_number": "HB 202 (DEMO)",
        "title": "School Bus Route Transparency",
        "session": "2026 Regular Session",
        "chamber": "House",
        "status": "Passed Committee",
        "jurisdiction_level": "state",
        "jurisdiction_name": "FL",
        "geo_scope_type": "statewide",
        "geo_scope_names": ["FL"],
        "introduced_date": date(2026, 1, 20),
        "last_action_date": date(2026, 2, 18),
        "last_action": "Passed Education Committee 12-1",
        "source_url": "https://www.myfloridahouse.gov/Sections/Bills/bills.aspx?BillId=202",
        "source_system": "legiscan",
        "sponsor": "Rep. K. Whitfield",
        "what_it_does": "This bill requires every school district to publish its bus routes and estimated stop times on the district website, updated within 5 business days of any change. Districts already publishing this through a third-party app are considered compliant.",
        "who_it_affects": "Public school districts statewide, and parents/guardians of students who ride the bus.",
    },
    {
        "bill_number": "SB 305 (DEMO)",
        "title": "Short-Term Rental Registration in Large Counties",
        "session": "2026 Regular Session",
        "chamber": "Senate",
        "status": "Introduced",
        "jurisdiction_level": "state",
        "jurisdiction_name": "FL",
        "geo_scope_type": "county",
        "geo_scope_names": ["Miami-Dade County"],
        "introduced_date": date(2026, 2, 1),
        "last_action_date": date(2026, 2, 1),
        "last_action": "Filed",
        "source_url": "https://www.flsenate.gov/Session/Bill/2026/0305",
        "source_system": "legiscan",
        "sponsor": "Sen. M. Reyes",
        "what_it_does": "This bill lets counties with more than 500,000 residents require short-term rental owners to register their property with the county tax collector before advertising it, and charge up to $150/year to cover the cost of running the registry. It does not let a county cap the number of rentals or restrict them to certain neighborhoods.",
        "who_it_affects": "Short-term rental property owners in Florida's largest counties (Miami-Dade qualifies), and county tax collector offices.",
    },
    {
        "bill_number": "HB 410 (DEMO)",
        "title": "Jacksonville Port Authority Infrastructure Funding",
        "session": "2026 Regular Session",
        "chamber": "House",
        "status": "In Committee",
        "jurisdiction_level": "state",
        "jurisdiction_name": "FL",
        "geo_scope_type": "county",
        "geo_scope_names": ["Duval County"],
        "introduced_date": date(2026, 1, 28),
        "last_action_date": date(2026, 2, 10),
        "last_action": "Referred to Transportation & Infrastructure Committee",
        "source_url": "https://www.myfloridahouse.gov/Sections/Bills/bills.aspx?BillId=410",
        "source_system": "legiscan",
        "sponsor": "Rep. D. Okafor",
        "what_it_does": "This bill directs $18 million in state infrastructure funds to channel-deepening and terminal upgrades at the Jacksonville Port Authority (JAXPORT) over two fiscal years.",
        "who_it_affects": "JAXPORT and Duval County, port-dependent employers (logistics, shipping, manufacturing) in the Jacksonville area.",
    },
    {
        "bill_number": "MIA-2026-014 (DEMO)",
        "title": "Ordinance Establishing Affordable Housing Density Bonus in Transit Corridors",
        "session": "2026",
        "chamber": "City Commission",
        "status": "First Reading",
        "jurisdiction_level": "city",
        "jurisdiction_name": "Miami",
        "geo_scope_type": "city",
        "geo_scope_names": ["Miami-Dade County"],
        "introduced_date": date(2026, 1, 15),
        "last_action_date": date(2026, 2, 5),
        "last_action": "Passed First Reading",
        "source_url": "https://miami.legistar.com/LegislationDetail.aspx?ID=2026014",
        "source_system": "legistar",
        "sponsor": "Commissioner R. Alonso",
        "what_it_does": "This ordinance allows developers to build taller, denser apartment buildings than normally permitted along Miami's Metrorail and bus rapid transit corridors, if at least 20% of the units are reserved as affordable housing for 30 years.",
        "who_it_affects": "Renters near transit corridors, real estate developers, and neighborhoods adjacent to Metrorail/BRT lines.",
    },
    {
        "bill_number": "MIA-2026-021 (DEMO)",
        "title": "Ordinance Amending Nighttime Construction Noise Limits",
        "session": "2026",
        "chamber": "City Commission",
        "status": "Introduced",
        "jurisdiction_level": "city",
        "jurisdiction_name": "Miami",
        "geo_scope_type": "city",
        "geo_scope_names": ["Miami-Dade County"],
        "introduced_date": date(2026, 2, 4),
        "last_action_date": date(2026, 2, 4),
        "last_action": "Referred to Neighborhoods Committee",
        "source_url": "https://miami.legistar.com/LegislationDetail.aspx?ID=2026021",
        "source_system": "legistar",
        "sponsor": "Commissioner J. Pierre",
        "what_it_does": "This ordinance lowers the allowed construction noise limit between 10pm and 7am from 75 to 65 decibels, and requires contractors to post a permit-visible noise complaint phone number at the job site.",
        "who_it_affects": "Residents living near active construction sites, and construction/development contractors operating within city limits.",
    },
    {
        "bill_number": "JAX-2026-009 (DEMO)",
        "title": "Resolution Approving Flood Mitigation Infrastructure Study",
        "session": "2026",
        "chamber": "City Council",
        "status": "Adopted",
        "jurisdiction_level": "city",
        "jurisdiction_name": "Jacksonville",
        "geo_scope_type": "city",
        "geo_scope_names": ["Duval County"],
        "introduced_date": date(2026, 1, 10),
        "last_action_date": date(2026, 1, 27),
        "last_action": "Adopted 17-0",
        "source_url": "https://jacksonville.legistar.com/LegislationDetail.aspx?ID=2026009",
        "source_system": "legistar",
        "sponsor": "Council Member T. Brooks",
        "what_it_does": "This resolution funds a $500,000 engineering study of flood mitigation options (stormwater pumps, seawall upgrades) for low-lying neighborhoods along the St. Johns River, with results due within 12 months.",
        "who_it_affects": "Residents of flood-prone Jacksonville neighborhoods along the St. Johns River, and the city's Public Works department.",
    },
    {
        "bill_number": "JAX-2026-015 (DEMO)",
        "title": "Ordinance Simplifying Small Business Occupational Licensing",
        "session": "2026",
        "chamber": "City Council",
        "status": "In Committee",
        "jurisdiction_level": "city",
        "jurisdiction_name": "Jacksonville",
        "geo_scope_type": "city",
        "geo_scope_names": ["Duval County"],
        "introduced_date": date(2026, 2, 2),
        "last_action_date": date(2026, 2, 12),
        "last_action": "Referred to Rules Committee",
        "source_url": "https://jacksonville.legistar.com/LegislationDetail.aspx?ID=2026015",
        "source_system": "legistar",
        "sponsor": "Council Member S. Nguyen",
        "what_it_does": "This ordinance combines five separate small-business license applications into a single online form and cuts the standard review time from 30 to 10 business days for businesses with fewer than 10 employees.",
        "who_it_affects": "New small business owners applying for a license in Jacksonville, and the city's Licensing & Permits office.",
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        for row in SAMPLE_BILLS:
            entity = Entity(
                entity_type="bill",
                name=row["title"],
                jurisdiction_level=row["jurisdiction_level"],
                jurisdiction_name=row["jurisdiction_name"],
                external_ids={"seed_demo_id": row["bill_number"]},
            )
            db.add(entity)
            db.flush()

            source = Source(
                url=row["source_url"],
                document_reference=row["bill_number"],
                publisher=f"{row['jurisdiction_name']} via {row['source_system']}",
                source_type="legiscan_bill" if row["source_system"] == "legiscan" else "legistar_agenda",
                retrieved_at=NOW,
                metadata_json={"seed": True},
            )
            db.add(source)
            db.flush()

            bill = Bill(
                entity_id=entity.id,
                bill_number=row["bill_number"],
                session=row["session"],
                chamber=row["chamber"],
                status=row["status"],
                introduced_date=row["introduced_date"],
                last_action_date=row["last_action_date"],
                last_action=row["last_action"],
                full_text_url=row["source_url"],
                source_system=row["source_system"],
                geo_scope_type=row["geo_scope_type"],
                geo_scope_names=row["geo_scope_names"],
            )
            db.add(bill)
            db.flush()

            sponsor = Entity(
                entity_type="person",
                name=row["sponsor"],
                jurisdiction_level=row["jurisdiction_level"],
                jurisdiction_name=row["jurisdiction_name"],
                external_ids={},
            )
            db.add(sponsor)
            db.flush()
            db.add(
                Relationship(
                    from_entity_id=sponsor.id,
                    to_entity_id=entity.id,
                    relationship_type="sponsor",
                    source_id=source.id,
                )
            )

            for claim_type in ("what_it_does", "who_it_affects"):
                claim = Claim(
                    bill_entity_id=entity.id,
                    claim_type=claim_type,
                    claim_text=row[claim_type],
                    generated_by="seed_demo_data",
                )
                db.add(claim)
                db.flush()
                db.add(ClaimSource(claim_id=claim.id, source_id=source.id))

        db.commit()
        print(f"Seeded {len(SAMPLE_BILLS)} sample bills.")

        boundary_count = load_sample_boundaries(db)
        print(f"Loaded {boundary_count} sample county/state boundary polygons.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
