"""titled_instrument against real titles from the county Legistar clients
(200 newest matters each, sampled 2026-10-27). Precision over recall: a title
that only mentions an instrument in a later clause stays the source's own type."""

import pytest

from app.pipeline.legistar import CLIENT_JURISDICTIONS, titled_instrument

LEGISLATION = [
    ("Resolution recognizing October 2026 as Filipino American History Month- District 5", "Resolution"),
    ("Ordinance Amending Chapter 102, Article IV, Division 3 of the Brevard County Code to Make Data Centers Ineligible", "Ordinance"),
    ("Tentative Approval of a Resolution Adopting the County’s Budget for FY 2026-2027", "Resolution"),
    ("Adoption of Resolutions Approving the FY 2026-2027 Final Budget for Dependent Special Districts", "Resolution"),
    ("Request Approval of a Resolution to Establish Speed Limits on Roadways Within Rainbow Lakes Estates (Budget Impact - None)", "Resolution"),
    ("Request Approval to Schedule and Advertise a Public Hearing to Consider an Ordinance Amending Chapter 5", "Ordinance"),
    ("ADOPTION OF A RESOLUTION ACCEPTING AND APPROVING A FIFTY-FOOT (50’) UTILITY EASEMENT", "Resolution"),
    ("SECOND PUBLIC HEARING TO CONSIDER ADOPTION OF AN ORDINANCE ESTABLISHING A TEMPORARY INTERIM PLANNING PERIOD", "Ordinance"),
    ("Adopt a Resolution Setting Speed Limits on Seven Oaks Drive and Seven Oaks Street", "Resolution"),
    ("SET HEARING (LDCT-2026-23 Triple E Management) to consider the adoption of an applicant-initiated ordinance amending the Land Development Code", "Ordinance"),
    ("Approve and authorize the Chairman to execute a Resolution naming an Unnamed Right of Way to Fern Park Boulevard", "Resolution"),
    ("Land Development Code Amendment - Consider an Ordinance amending Chapter 2- Definitions", "Ordinance"),
    ("An Ordinance Amending Orange County Code Chapter 37, Article I, Entitled “Orange County Water Rules”", "Ordinance"),
    ("Approval and execution of Resolution of the Orange County Board of County Commissioners regarding establishing a process", "Resolution"),
    ("Resolution adopting the updated 2026 Utilities Policy Manual.", "Resolution"),
]

NOT_LEGISLATION = [
    "Acknowledge receipt of the FY 2025-2026 Parrish Medical Center Revenue and Expense Budget and Millage Resolution.",
    "Request Approval of Mediated Settlement Agreement in Request for Dispute Resolution Pursuant to Section 70.51, Florida Statutes",
    "Request Approval of a Locally Funded Agreement between the State of Florida Department of Transportation and Marion County with a Supporting Resolution",
    "Approve and authorize the Chairman to sign the Supplemental Agreement No.02 to the Joint Participation Agreement",
    "Rescind Resolution Nos. 2025-134 and 2026-023 in their entirety related to the State Housing Initiative Partnership",
    "Procurement Ordinance Update. (Procurement Division)",
    "County Commission New Business: Pertinent and timely Committee/Board updates, policy considerations, administrative matters",
    "Appointment of a Special Magistrate to Consider Matters Related to the Administration of the Code",
    "",
]


@pytest.mark.parametrize("title,expected", LEGISLATION)
def test_reads_the_instrument_from_a_title(title, expected):
    assert titled_instrument(title) == expected


@pytest.mark.parametrize("title", NOT_LEGISLATION)
def test_leaves_other_titles_alone(title):
    assert titled_instrument(title) is None


def test_a_long_compound_item_is_not_read_for_a_clause_buried_in_it():
    long_title = (
        "Approve the ranking list and authorize staff to negotiate rates in accordance with Section 287.055, "
        "Florida Statutes, and authorize the Purchasing and Contracts Division to execute Master Services "
        + "Agreement for Construction Manager at Risk Services for the Indoor Sports Complex; and approve " * 3
        + "the Chairman to execute a Resolution"
    )
    assert len(long_title) > 300
    assert titled_instrument(long_title) is None


def test_the_county_clients_that_read_titles_are_county_level_and_nightly():
    readers = {k: v for k, v in CLIENT_JURISDICTIONS.items() if v.get("instrument_from_title")}
    assert set(readers) == {"pinellas", "brevardfl", "marionfl", "martin", "polkcountyfl", "seminolecountyfl", "occompt"}
    assert all(v["level"] == "county" and v["nightly"] and v["label"] and v["note"] for v in readers.values())
