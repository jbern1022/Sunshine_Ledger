from datetime import date

import pytest
from sqlalchemy import select

from app.federal.bills import upsert_bill
from app.federal.congress_api import CongressClient
from app.federal.places import find_places
from app.federal.texts import analyze_text, gpo_text, store_version, sync_texts, version_links
from app.models import Bill, Entity, FederalBillText, FederalPlaceFinding

BILL_TEXT = """\
SEC. 101. DEFENSE CONSTRUCTION.

    (a) In General.--The Secretary shall carry out a project at MacDill Air Force Base, Florida, in the amount of $12,000,000. The
Secretary may also repair the seawall at Naval Station Mayport.

SEC. 102. FLOOD MITIGATION.

    There is authorized $2,500,000 for the City of Tampa, Florida, for stormwater work, and $1,000,000 for Miami-Dade County,
Florida, for canal dredging. Restoration of the Everglades shall continue under the plan.

SEC. 103. NATIONWIDE RULE.

    Each eligible employer in any State shall file a report. Orange County, California, is excluded. The Florida Avenue NW entrance
is closed. Disaster declaration DR-4673-FL is extended.

SEC. 104. COURTS.

    The United States District Court for the Southern District of Florida shall sit in Fort Lauderdale, Florida.
"""


def terms(findings):
    return {(f.kind, f.matched_term) for f in findings}


def test_named_florida_places_are_found_with_their_exact_sentence():
    found = find_places(BILL_TEXT)
    t = terms(found)
    assert ("named_place", "MacDill Air Force Base") in t
    assert ("municipality", "Tampa") in t and ("county", "Miami-Dade County") in t
    assert ("named_place", "Everglades") in t and ("named_place", "Naval Station Mayport") in t
    assert ("disaster", "DR-4673-FL") in t
    assert ("municipality", "Fort Lauderdale") in t
    tampa = next(f for f in found if f.matched_term == "Tampa")
    assert tampa.counties == ("Hillsborough",) and tampa.section.startswith("SEC. 102")
    assert tampa.quote_text == BILL_TEXT[tampa.char_start:tampa.char_end]  # copied exactly, offsets honest
    assert "City of Tampa, Florida" in tampa.quote_text


def test_things_that_are_not_florida_are_not_found():
    found = find_places(BILL_TEXT)
    names = {f.matched_term for f in found}
    assert "Orange County" not in names                      # Orange County, California
    assert not any("Florida Avenue" in f.quote_text and f.kind == "state" for f in found)
    assert find_places("The Secretary shall report to Congress. Each State shall comply.") == []
    assert find_places("Orange County, Florida, shall receive funds.")[0].matched_term == "Orange County"


def test_a_bare_county_name_counts_only_when_the_sentence_says_florida():
    assert terms(find_places("Funds go to Lee County for roads.")) == set()
    assert ("county", "Lee County") in terms(find_places("Funds go to Lee County for roads in Florida."))


def test_a_generic_florida_mention_is_one_finding_unless_a_specific_place_names_the_sentence():
    only_state = find_places("This section applies to the State of Florida and its agencies.")
    assert [(f.kind, f.matched_term) for f in only_state] == [("state", "Florida")]
    specific = find_places("Work at Eglin Air Force Base in Florida shall continue.")
    assert [(f.kind) for f in specific] == ["named_place"]


# --- storing text and analysing it ------------------------------------------------

def _bill(db, delegation=True):
    return upsert_bill(db, congress=119, slug="hr", number=10, title="Test", delegation=delegation)


def test_versions_are_kept_findings_follow_and_bill_text_mirrors_the_latest(db_session):
    e = _bill(db_session)
    v1 = store_version(db_session, e, version_type="Introduced in House", version_date=date(2026, 3, 1), url="https://x/ih.htm",
                       text="Funds for the City of Tampa, Florida, for roads.")
    v2 = store_version(db_session, e, version_type="Engrossed in House", version_date=date(2026, 6, 1), url="https://x/eh.htm",
                       text="Funds for the City of Tampa, Florida, and Pensacola, Florida, for roads.")
    assert len(v1.findings) == 1 and len(v2.findings) == 2
    assert e.bill.full_text == v2.text                      # the latest version
    assert store_version(db_session, e, version_type="x", version_date=None, url="https://x/eh.htm", text="again") is None
    assert len(db_session.execute(select(FederalBillText)).scalars().all()) == 2


def test_reanalysis_replaces_findings_instead_of_stacking_them(db_session):
    e = _bill(db_session)
    ft = store_version(db_session, e, version_type="Introduced", version_date=None, url="u", text="Work at Eglin Air Force Base.")
    first = db_session.execute(select(FederalPlaceFinding)).scalars().all()
    analyze_text(db_session, ft)
    assert len(db_session.execute(select(FederalPlaceFinding)).scalars().all()) == len(first) == 1


def test_gpo_page_is_reduced_to_its_printed_text():
    html = "<html><body><pre>\n[Congressional Bills 119th Congress]\n&lt;DOC&gt;\n\n   Sec. 1.  Tampa, Florida.   \n</pre></body></html>"
    assert gpo_text(html) == "[Congressional Bills 119th Congress]\n<DOC>\n\n   Sec. 1.  Tampa, Florida."


def test_version_links_prefer_printed_text_and_skip_pdf_only():
    payload = {"textVersions": [
        {"date": "2026-03-01T05:00:00Z", "type": "Introduced in House", "formats": [
            {"type": "PDF", "url": "https://x/a.pdf"}, {"type": "Formatted Text", "url": "https://x/a.htm"}]},
        {"date": None, "type": "Engrossed", "formats": [{"type": "PDF", "url": "https://x/b.pdf"}]},
    ]}
    assert version_links(payload) == [{"type": "Introduced in House", "date": date(2026, 3, 1), "url": "https://x/a.htm"}]


class FakeApi:
    def __init__(self, payloads):
        self.payloads, self.paths = payloads, []

    def get(self, path, **params):
        self.paths.append(path)
        return self.payloads.get(path, {})


def test_sync_texts_covers_only_delegation_bills_and_is_resumable(db_session):
    mine = _bill(db_session)
    other = upsert_bill(db_session, congress=119, slug="hr", number=11, title="Not ours")
    api = FakeApi({"/bill/119/hr/10/text": {"textVersions": [
        {"date": "2026-03-01T05:00:00Z", "type": "Introduced in House",
         "formats": [{"type": "Formatted Text", "url": "https://x/ih.htm"}]}]}})
    pages = {"https://x/ih.htm": "<pre>Funds for Key West, Florida.</pre>"}
    out = sync_texts(db_session, api, lambda url: pages.get(url), limit=None)
    assert out == {"bills": 1, "versions": 1, "findings": 1, "no_text": 0}
    assert api.paths == ["/bill/119/hr/10/text"]           # the non-delegation bill is never asked about
    again = sync_texts(db_session, api, lambda url: pages.get(url), limit=None)
    assert again["versions"] == 0
    assert other.bill.full_text is None


def test_florida_places_endpoint_labels_findings_and_states_its_limits(client, db_session):
    e = _bill(db_session)
    store_version(db_session, e, version_type="Introduced in House", version_date=date(2026, 3, 1), url="https://x/ih.htm",
                  text="SEC. 5. Funds for the City of Tampa, Florida, for roads.")
    body = client.get(f"/bills/{e.id}/florida-places").json()
    assert body["label"].startswith("Automatically found") and "does not mean Florida is unaffected" in body["not_covered"]
    assert body["text_version"]["type"] == "Introduced in House"
    f = body["findings"][0]
    assert (f["kind"], f["name"], f["counties"], f["section"]) == ("municipality", "Tampa", ["Hillsborough"], "SEC. 5. Funds for the City of Tampa, Florida, for roads.")
    state = Entity(entity_type="bill", name="State", jurisdiction_level="state", jurisdiction_name="FL", external_ids={}, attributes={})
    db_session.add(state)
    db_session.flush()
    db_session.add(Bill(entity_id=state.id, bill_number="HB 1", session="2026", status="Introduced", source_system="legiscan"))
    db_session.flush()
    assert client.get(f"/bills/{state.id}/florida-places").status_code == 404
    no_text = _bill_2 = upsert_bill(db_session, congress=119, slug="hr", number=99, title="No text", delegation=True)
    assert client.get(f"/bills/{no_text.id}/florida-places").json()["findings"] == []


# --- regressions found by running the detector on the real FY2026 NDAA (H.R. 3838) ------

def test_a_sentence_wrapped_over_several_lines_is_kept_whole():
    text = ("SEC. 9. LAND.\n\n    Land conveyance, Sigsbee Park Annex, Naval Air Station, Key\n"
            "    West, Florida. The Secretary shall report within 30 days.\n")
    f = find_places(text)[0]
    assert f.matched_term == "Key West"
    assert " ".join(f.quote_text.split()) == "Land conveyance, Sigsbee Park Annex, Naval Air Station, Key West, Florida."
    assert f.quote_text == text[f.char_start:f.char_end]


def test_a_list_of_states_does_not_make_georgia_a_florida_place():
    names = {f.matched_term for f in find_places("It covers South Carolina, Georgia, Florida, Louisiana, and Texas.")}
    assert "Georgia" not in names and "South Carolina" not in names


def test_table_rows_are_findings_on_their_own_line_and_a_florida_heading_is_not_repeated():
    table = ("SEC. 2301. AUTHORIZED AIR FORCE CONSTRUCTION.\n\n"
             "Florida........................................\n"
             "  Eglin Air Force Base...........................      $166,000,000\n"
             "  MacDill Air Force Base.........................       $74,000,000\n"
             "Florida........................................\n")
    found = find_places(table)
    # the heading names Florida once for the section, not once per repeat
    assert [f.matched_term for f in found] == ["Florida", "Eglin Air Force Base", "MacDill Air Force Base"]
    assert found[1].quote_text.startswith("Eglin Air Force Base") and "$166,000,000" in found[1].quote_text


def test_abbreviations_do_not_end_a_sentence():
    f = find_places("The U.S. Army shall repair the facility at St. Augustine, Florida. It shall start soon.")[0]
    assert f.quote_text.startswith("The U.S. Army") and f.quote_text.endswith("Florida.")


def test_a_large_bill_is_scanned_in_seconds():
    import time

    big = ("SEC. 1. TEXT.\n\n" + ("The Secretary shall, in consultation with the Administrator, carry out the program, Washington, D.C., and Texas. " * 6 + "\n\n") * 8000
           + "Work at Eglin Air Force Base, Florida.\n")
    t = time.monotonic()
    found = find_places(big)
    assert time.monotonic() - t < 15 and any(f.matched_term == "Eglin Air Force Base" for f in found)
