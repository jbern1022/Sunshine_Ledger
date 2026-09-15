"""Seed the 13 badge Tags and a first-pass curated SubjectMapping table.

The mapping rows below are a DRAFT (documented 2026-09-15) built from
general knowledge of typical FL Subject Index terminology, NOT a live
export of LegiScan's actual distinct raw-subject strings across the
ingested dataset. Treat every mapping as provisional -- run the real
distinct-subject list against this table and patch gaps before relying on
tag coverage for anything user-facing.

Idempotent: safe to re-run (upserts by slug / raw_subject).

Usage:
    python -m app.pipeline.topic_tagging_seed
"""

from __future__ import annotations

from sqlalchemy import select

from app.db import SessionLocal
from app.models.tag import GOVERNANCE_SLUG, SubjectMapping, Tag

# (slug, label)
TAGS: list[tuple[str, str]] = [
    ("housing", "Housing"),
    ("infrastructure_transportation", "Infrastructure/Transportation"),
    ("education", "Education"),
    ("healthcare", "Healthcare"),
    ("environment", "Environment"),
    ("public_safety_criminal_justice", "Public Safety/Criminal Justice"),
    ("taxes_budget", "Taxes/Budget"),
    ("labor_employment", "Labor/Employment"),
    ("agriculture", "Agriculture"),
    ("elections_government", "Elections/Government"),
    ("consumer_protection", "Consumer Protection"),
    ("utilities_energy", "Utilities/Energy"),
    (GOVERNANCE_SLUG, "Governance"),
]

# raw_subject -> tag slug. Draft only -- see module docstring.
SUBJECT_MAPPINGS: dict[str, str] = {
    "AFFORDABLE HOUSING": "housing",
    "HOUSING FINANCE": "housing",
    "LANDLORD AND TENANT": "housing",
    "MOBILE HOMES": "housing",
    "MANUFACTURED HOMES": "housing",
    "REAL PROPERTY": "housing",
    "ROADS AND HIGHWAYS": "infrastructure_transportation",
    "TRANSPORTATION": "infrastructure_transportation",
    "MOTOR VEHICLES": "infrastructure_transportation",
    "RAILROADS": "infrastructure_transportation",
    "AVIATION": "infrastructure_transportation",
    "PORTS": "infrastructure_transportation",
    "PUBLIC WORKS": "infrastructure_transportation",
    "SCHOOLS AND SCHOOL DISTRICTS": "education",
    "EDUCATION": "education",
    "COLLEGES AND UNIVERSITIES": "education",
    "CHARTER SCHOOLS": "education",
    "STUDENT FINANCIAL AID": "education",
    "HEALTH CARE": "healthcare",
    "HOSPITALS": "healthcare",
    "MEDICAID": "healthcare",
    "INSURANCE-HEALTH": "healthcare",
    "MENTAL HEALTH": "healthcare",
    "PHARMACIES AND PHARMACISTS": "healthcare",
    "ENVIRONMENTAL PROTECTION": "environment",
    "WATER RESOURCES": "environment",
    "WATER MANAGEMENT DISTRICTS": "environment",
    "POLLUTION": "environment",
    "WILDLIFE": "environment",
    "CONSERVATION": "environment",
    "CRIMES": "public_safety_criminal_justice",
    "CRIMINAL PROCEDURE": "public_safety_criminal_justice",
    "LAW ENFORCEMENT": "public_safety_criminal_justice",
    "CORRECTIONAL FACILITIES": "public_safety_criminal_justice",
    "FIREARMS AND WEAPONS": "public_safety_criminal_justice",
    "EMERGENCY MANAGEMENT": "public_safety_criminal_justice",
    "TAXATION": "taxes_budget",
    "TAX EXEMPTIONS": "taxes_budget",
    "APPROPRIATIONS": "taxes_budget",
    "STATE BUDGET": "taxes_budget",
    "AD VALOREM TAXATION": "taxes_budget",
    "LABOR": "labor_employment",
    "EMPLOYMENT": "labor_employment",
    "WORKERS' COMPENSATION": "labor_employment",
    "UNEMPLOYMENT COMPENSATION": "labor_employment",
    "OCCUPATIONAL LICENSING": "labor_employment",
    "AGRICULTURE": "agriculture",
    "FOOD SAFETY": "agriculture",
    "FORESTRY": "agriculture",
    "FISHERIES": "agriculture",
    "ELECTIONS": "elections_government",
    "CAMPAIGN FINANCING": "elections_government",
    "LOCAL GOVERNMENT": "elections_government",
    "STATE GOVERNMENT": "elections_government",
    "PUBLIC RECORDS": "elections_government",
    "CONSUMER PROTECTION": "consumer_protection",
    "UNFAIR TRADE PRACTICES": "consumer_protection",
    "TELEMARKETING": "consumer_protection",
    "DEBT COLLECTION": "consumer_protection",
    "PUBLIC UTILITIES": "utilities_energy",
    "ELECTRIC UTILITIES": "utilities_energy",
    "TELECOMMUNICATIONS": "utilities_energy",
    "ENERGY": "utilities_energy",
    # Deliberately unmapped -- routes to Governance via resolve_tag_for_subject,
    # not because it belongs in Governance conceptually, but as the stress-test
    # case called out when this taxonomy was drafted (2026-09-15).
}


def seed() -> None:
    db = SessionLocal()
    try:
        tags_by_slug: dict[str, Tag] = {}
        for slug, label in TAGS:
            tag = db.execute(select(Tag).where(Tag.slug == slug)).scalar_one_or_none()
            if tag is None:
                tag = Tag(slug=slug, label=label, active=True)
                db.add(tag)
                db.flush()
            tags_by_slug[slug] = tag
        db.commit()
        print(f"Seeded {len(TAGS)} tags.")

        added = 0
        for raw_subject, slug in SUBJECT_MAPPINGS.items():
            existing = db.execute(
                select(SubjectMapping).where(SubjectMapping.raw_subject == raw_subject)
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(SubjectMapping(raw_subject=raw_subject, tag_id=tags_by_slug[slug].id))
            added += 1
        db.commit()
        print(f"Seeded {added} new subject mappings ({len(SUBJECT_MAPPINGS) - added} already present).")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
