"""Roadmap Step 3: push ONE bill through the full conceptual pipeline by hand
— pull, summarize, geo-tag, store, display with a source link — to prove the
system's shape before Step 4 (automating the real LegiScan integration).

Deliberately hardcodes bill data inline rather than calling the LegiScan
client, matching the roadmap's "by hand" framing. Swap in a real bill
(title/text/url) pulled manually from https://legiscan.com/FL once you have
one, to prove the shape against a real bill rather than a sample.

Usage:
    python -m app.pipeline.one_bill_by_hand
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.db import SessionLocal
from app.models import Bill, Entity, Source
from app.pipeline.geotag import tag_bill_geography
from app.pipeline.summarize import OllamaClient, generate_bill_summaries
from app.models import Claim, ClaimSource

# Step "pull" — manually copied from a real (or, here, representative sample) bill.
SAMPLE_BILL = {
    "bill_number": "SB-0002 (SAMPLE)",
    "title": "An Act Relating to Local Government Short-Term Rental Registration",
    "session": "2026 Regular Session",
    "chamber": "Senate",
    "status": "In Committee",
    "introduced_date": date(2026, 1, 12),
    "bill_text": (
        "Section 1. Any county with a population greater than 500,000 may require owners of "
        "short-term rental properties, defined as residential dwellings rented for fewer than "
        "30 consecutive days, to register the property with the county tax collector prior to "
        "advertising the property for rent, including in Miami-Dade County. Section 2. Counties "
        "adopting a registration requirement under this section may charge a registration fee "
        "not to exceed $150 per property per year."
    ),
    "source_url": "https://www.flsenate.gov/Session/Bill/2026/0002",
}


def run() -> None:
    db = SessionLocal()
    try:
        # --- pull + store, with source attached at write-time (BRD 5.1) ---
        entity = Entity(
            entity_type="bill",
            name=SAMPLE_BILL["title"],
            jurisdiction_level="state",
            jurisdiction_name="FL",
            external_ids={"manual_demo": "one_bill_by_hand"},
        )
        db.add(entity)
        db.flush()

        source = Source(
            url=SAMPLE_BILL["source_url"],
            document_reference=SAMPLE_BILL["bill_number"],
            publisher="Florida Senate",
            source_type="legiscan_bill",
            retrieved_at=datetime.now(timezone.utc),
            metadata_json={"note": "pulled manually for Roadmap Step 3 proof-of-shape"},
        )
        db.add(source)
        db.flush()

        # --- geo-tag based on bill text (BRD 5.3) ---
        geo = tag_bill_geography(
            SAMPLE_BILL["bill_text"], default_scope_type="statewide", default_scope_names=["FL"]
        )

        bill = Bill(
            entity_id=entity.id,
            bill_number=SAMPLE_BILL["bill_number"],
            session=SAMPLE_BILL["session"],
            chamber=SAMPLE_BILL["chamber"],
            status=SAMPLE_BILL["status"],
            introduced_date=SAMPLE_BILL["introduced_date"],
            full_text_url=SAMPLE_BILL["source_url"],
            source_system="legiscan",
            geo_scope_type=geo.scope_type,
            geo_scope_names=geo.scope_names,
        )
        db.add(bill)
        db.flush()

        # --- summarize (BRD 5.2) ---
        client = OllamaClient()
        summaries = generate_bill_summaries(
            SAMPLE_BILL["bill_number"], SAMPLE_BILL["title"], SAMPLE_BILL["bill_text"], client=client
        )

        for claim_type, text in summaries.items():
            claim = Claim(
                bill_entity_id=entity.id,
                claim_type=claim_type,
                claim_text=text,
                generated_by=f"llm:{client.model}",
            )
            db.add(claim)
            db.flush()
            db.add(ClaimSource(claim_id=claim.id, source_id=source.id))

        db.commit()

        # --- display (proves the shape end-to-end) ---
        print(f"\nStored bill entity {entity.id}\n")
        print(f"{bill.bill_number} — {entity.name}")
        print(f"Status: {bill.status} | Geo scope: {bill.geo_scope_type} {bill.geo_scope_names}")
        print(f"\nWhat it does:\n  {summaries['what_it_does']}")
        print(f"\nWho it affects:\n  {summaries['who_it_affects']}")
        print(f"\nSource (1): {source.url}")

    finally:
        db.close()


if __name__ == "__main__":
    run()
