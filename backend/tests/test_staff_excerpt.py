from datetime import date

from app.api.staff_excerpt import tidy
from app.models import StaffAnalysis

# Shaped like HB 1389's HAT analysis (h1389z1.HAT.PDF), cut down.
ANALYSIS = """I. SUMMARY
Something.
III. Effect of Proposed Changes:
Live Local Act
The bill amends the Live Local Act (Act) and requires:
 Local governments1 to authorize multifamily and mixed-use residential as allowable uses on property
owned by a county, municipality, or school district; and
 A proposed development to be within the
geographic boundaries of the county.
The bill takes effect July 1, 2026.
IV. Constitutional Issues:
None.
V. Fiscal Impact Statement:
LOCAL GOVERNMENT:
The bill has an indeterminate impact on local governments that are subject to the bill's requirements to authorize
the development of affordable housing.
PRIVATE SECTOR:
The bill has an indeterminate positive impact on the private sector.
VI. Technical Deficiencies:
None.
"""


def test_tidy_joins_wraps_and_keeps_every_word():
    out = tidy("Live Local Act\nThe bill amends the Act and requires:\n Local governments1 to authorize uses on property\nowned by a county; and\n A development to be within the\ngeographic boundaries.")
    assert out.split("\n\n") == [
        "Live Local Act",
        "The bill amends the Act and requires:",
        "• Local governments1 to authorize uses on property owned by a county; and",
        "• A development to be within the geographic boundaries.",
    ]


def test_page_headers_are_dropped_and_footnotes_moved_to_notes():
    # HB 1389, page 2 -> 3 of h1389z1.HAT.PDF, as extracted.
    raw = ("\uf0b7 A proposed development to be a party to the development application; and\n"
           "1 Local government means any county or municipality. See s. 163.3164(29), F.S.\n"
           "2 \u201cReligious institution\u201d means any church, synagogue, or other established physical place for worship at which nonprofit\n"
           "religious services and activities are regularly conducted. S. 170.201(2), F.S.\n"
           "CS/CS/HB 1389\n"
           "\uf0b7 A house of public worship to continue on the property.\n"
           "The bill specifies that a development may consist of an assemblage of parcels.\n"
           "3 Id.\n"
           "The bill takes effect July 1, 2026.")
    assert tidy(raw).split("\n\n") == [
        "• A proposed development to be a party to the development application; and",
        "• A house of public worship to continue on the property.",
        "The bill specifies that a development may consist of an assemblage of parcels.",
        "The bill takes effect July 1, 2026.",
        "Notes",
        "[1] Local government means any county or municipality. See s. 163.3164(29), F.S.",
        "[2] \u201cReligious institution\u201d means any church, synagogue, or other established physical place for worship "
        "at which nonprofit religious services and activities are regularly conducted. S. 170.201(2), F.S.",
        "[3] Id.",
    ]


def test_a_number_starting_a_wrapped_line_is_not_a_footnote():
    assert tidy("a parcel separated by no more than\n15 feet of right-of-way.") == "a parcel separated by no more than 15 feet of right-of-way."


def test_tidy_changes_only_whitespace_and_bullets():
    section = ANALYSIS.split("III. Effect of Proposed Changes:\n")[1].split("IV.")[0]
    words = lambda s: s.replace("", "•").split()
    assert words(tidy(section)) == words(section)


def _analysis(db, entity, sid, when, text, committee="Housing, Agriculture & Tourism Subcommittee"):
    db.add(StaffAnalysis(entity_id=entity.id, legiscan_supplement_id=sid, committee=committee,
                         analysis_date=when, source_url=f"https://flsenate.gov/{sid}.pdf", text=text))
    db.commit()


def test_bill_page_quotes_the_latest_analysis(client, db_session, bill_factory):
    entity = bill_factory()
    _analysis(db_session, entity, 1, date(2026, 2, 1), ANALYSIS.replace("Live Local Act\n", "Old version\n"), committee="Rules")
    _analysis(db_session, entity, 2, date(2026, 6, 29), ANALYSIS)
    s = client.get(f"/bills/{entity.id}").json()["staff_analysis"]
    assert s["committee"] == "Housing, Agriculture & Tourism Subcommittee"
    assert s["analysis_date"] == "2026-06-29"
    assert s["source_url"] == "https://flsenate.gov/2.pdf"
    assert s["effect"].startswith("Live Local Act\n\nThe bill amends the Live Local Act (Act) and requires:")
    assert "• Local governments1 to authorize multifamily" in s["effect"]
    assert s["fiscal"].startswith("LOCAL GOVERNMENT:\n\nThe bill has an indeterminate impact")
    assert (s["analyses_count"], s["is_latest"], s["truncated"]) == (2, True, False)


def test_an_analysis_without_either_section_falls_back_to_an_older_one(client, db_session, bill_factory):
    entity = bill_factory()
    _analysis(db_session, entity, 3, date(2026, 2, 1), ANALYSIS, committee="Rules")
    _analysis(db_session, entity, 4, date(2026, 3, 1), "A cover page with no sections.")
    s = client.get(f"/bills/{entity.id}").json()["staff_analysis"]
    assert (s["committee"], s["is_latest"]) == ("Rules", False)


def test_no_analysis_means_no_box(client, bill_factory):
    assert client.get(f"/bills/{bill_factory().id}").json()["staff_analysis"] is None
