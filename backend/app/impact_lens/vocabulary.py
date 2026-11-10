"""The attribute registry: what a reader can be asked, and what criteria may test.

Deliberately small. An attribute is added only when a real bill's provision
uses it. Bump VOCABULARY_VERSION on any change so stored criteria say which
vocabulary they were mapped against.

Privacy boundary (Product & Trust Foundation, Impact Lens, 2026-10-05): no
attribute may capture a dimension in FORBIDDEN_DIMENSIONS. A test enforces it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

VOCABULARY_VERSION = 3
# Version 3 only ADDED role values (flood_insurance_policyholder,
# medicare_beneficiary, small_employer), so a criteria row mapped at version 2
# is still exact under version 3 and keeps being served until the entry is
# remapped. A later change that removes or reinterprets a value must drop the
# older version from this list.
COMPATIBLE_VERSIONS = (2, 3)

# Dimensions the privacy boundary excludes from the anonymous Impact Lens.
# Matched as substrings of an attribute key, so "immigration_status" and
# "household_income_exact" are both refused.
FORBIDDEN_DIMENSIONS = (
    "political", "party", "immigration", "citizenship", "health", "disability",
    "religio", "race", "ethnic", "address", "income", "employer_name",
)

CHOICE = "choice"
NUMBER = "number"

OPS_BY_TYPE = {
    CHOICE: ("in", "not_in"),
    NUMBER: ("gte", "lte", "between"),
}

FLORIDA_COUNTIES = (
    "Alachua", "Baker", "Bay", "Bradford", "Brevard", "Broward", "Calhoun", "Charlotte", "Citrus",
    "Clay", "Collier", "Columbia", "DeSoto", "Dixie", "Duval", "Escambia", "Flagler", "Franklin",
    "Gadsden", "Gilchrist", "Glades", "Gulf", "Hamilton", "Hardee", "Hendry", "Hernando",
    "Highlands", "Hillsborough", "Holmes", "Indian River", "Jackson", "Jefferson", "Lafayette",
    "Lake", "Lee", "Leon", "Levy", "Liberty", "Madison", "Manatee", "Marion", "Martin",
    "Miami-Dade", "Monroe", "Nassau", "Okaloosa", "Okeechobee", "Orange", "Osceola", "Palm Beach",
    "Pasco", "Pinellas", "Polk", "Putnam", "St. Johns", "St. Lucie", "Santa Rosa", "Sarasota",
    "Seminole", "Sumter", "Suwannee", "Taylor", "Union", "Volusia", "Wakulla", "Walton",
    "Washington",
)


_MUNICIPALITIES_FILE = Path(__file__).resolve().parent.parent / "data" / "fl_municipalities.json"
_municipalities = json.loads(_MUNICIPALITIES_FILE.read_text())["municipalities"]
# municipality name -> the counties it lies in (a few span two)
MUNICIPALITY_COUNTIES: dict[str, tuple[str, ...]] = {m["name"]: tuple(m["counties"]) for m in _municipalities}


def county_value(name: str) -> str:
    return f"county:{name}"


def municipality_value(name: str) -> str:
    return f"municipality:{name}"


def jurisdiction_label(value: str) -> str:
    """'county:Duval' -> 'Duval County'; 'municipality:Miami' -> 'Miami (city, town or village)'."""
    kind, _, name = value.partition(":")
    return f"{name} County" if kind == "county" else f"{name} (municipality)"


@dataclass(frozen=True)
class Attribute:
    key: str
    label: str
    type: str  # CHOICE | NUMBER
    question: str
    values: tuple[str, ...] = ()  # CHOICE only
    audience: bool = False  # may be a criterion's audience (who the rule is about)


ROLE = Attribute(
    key="role",
    label="Role",
    type=CHOICE,
    question="Which best describes you in relation to this bill?",
    values=("renter", "landlord", "homeowner", "property_developer", "employer", "employee",
            "business_owner", "local_government", "insured", "healthcare_provider",
            # Nationwide categories for federal bills (owner-approved 2026-11-10).
            # Answers stay in the browser; none is stored or sent.
            "flood_insurance_policyholder", "medicare_beneficiary", "small_employer"),
    audience=True,
)
# One attribute for both levels so a single condition ("any county or city that
# ...") stays one OR-list. A reader answers county, then optionally municipality;
# a county value matches the reader's county, a municipality value matches the
# reader's municipality (and is unknown if they have not given one).
JURISDICTION = Attribute(
    key="jurisdiction",
    label="Location",
    type=CHOICE,
    question="Which Florida county do you live in, and which city, town or village (if any)?",
    values=tuple(county_value(c) for c in FLORIDA_COUNTIES) + tuple(municipality_value(m) for m in MUNICIPALITY_COUNTIES),
)
PROPERTY_TYPE = Attribute(
    key="property_type",
    label="Property Type",
    type=CHOICE,
    question="What kind of property?",
    values=("single_family", "multifamily", "commercial"),
)

REGISTRY: dict[str, Attribute] = {a.key: a for a in (ROLE, JURISDICTION, PROPERTY_TYPE)}

# Which of a reader's locations a role's rules are about. A place a bill names
# is compared with the reader's location of this kind, not always with where
# they live (docs/IMPACT_LENS_ROLE_LOCATIONS.md). Sent to the browser with every
# bill so the matcher keeps no copy; a test requires every role to be listed.
RESIDENCE, PROPERTY, BUSINESS = "residence", "property", "business"
ROLE_LOCATIONS: dict[str, str] = {
    "renter": RESIDENCE,
    "insured": RESIDENCE,
    # A government's own area is not a residence; kept as residence until the
    # model has a place for it.
    "local_government": RESIDENCE,
    "landlord": PROPERTY,
    "homeowner": PROPERTY,
    "property_developer": PROPERTY,
    "employer": BUSINESS,
    "business_owner": BUSINESS,
    "employee": BUSINESS,
    "healthcare_provider": BUSINESS,
    "flood_insurance_policyholder": PROPERTY,  # the insured property
    "medicare_beneficiary": RESIDENCE,
    "small_employer": BUSINESS,
}


def is_forbidden(key: str) -> bool:
    k = key.lower()
    return any(bad in k for bad in FORBIDDEN_DIMENSIONS)
