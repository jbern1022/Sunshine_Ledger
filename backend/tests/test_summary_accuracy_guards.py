"""Accuracy guards from the 2026-11-27 re-run (docs/grant-ready/ACCURACY_RERUN_2026-11-27.md).

Fixtures are the real records and the summaries the model wrote for them:
- H.B. 7019 (2026): the sunset was inverted ("remain in place unless it is repealed").
- S.B. 1758 (2026) and Margate 2026-319: status words on records not enacted.
- Miami R-26-0321: "requires" where the title only authorizes.
- Miami R-26-0331: "if awarded" dropped.
"""

import pytest

from app.pipeline.bill_layers_text import overstates_title_modal
from app.pipeline.summary_checks import (
    apply_sunset_rule,
    drops_condition,
    is_enacted,
    is_sunset_review,
    overstates_status,
    sunset_sentence,
)

H7019_TEXT = """A bill to be entitled
An act relating to a review under the Open Government
Sunset Review Act; amending s. 119.0712, F.S., which
provides an exemption from public record requirements
for certain information held by the Department of
Military Affairs; extending the scheduled
repeal date of the exemption; providing an effective
date.
Be It Enacted by the Legislature of the State of Florida:
Section 1. Subsection (4) of section 119.0712, Florida
Statutes, is amended to read:
(4) DEPARTMENT OF MILITARY AFFAIRS.—Information held by
the Department of Military Affairs is exempt
from s. 119.07(1) and s. 24(a), Art. I of the State
Constitution. This subsection is subject to
the Open Government Sunset Review Act in accordance with s.
119.15 and shall stand repealed on October 2, [added: 2031] [deleted: 2026,] unless
reviewed and saved from repeal through reenactment by the
Legislature.
Section 2. This act shall take effect upon becoming a law.
"""

H7019_SUMMARY = (
    "This bill extends the exemption from public record requirements for certain information held by the "
    "Department of Military Affairs. The exemption, which is based on federal law, allows the department to "
    "keep some information private. However, the department may still disclose information that is not "
    "exempt, after making any necessary redactions. The exemption will remain in place unless it is repealed "
    "by the Legislature on October 2, 2031."
)

R0321_TITLE = (
    "A RESOLUTION OF THE MIAMI CITY COMMISSION COMPUTING A PROPOSED MILLAGE RATE FOR THE DOWNTOWN DEVELOPMENT "
    "AUTHORITY OF THE CITY OF MIAMI, FLORIDA (“MIAMI DDA”) FOR THE FISCAL YEAR BEGINNING OCTOBER 1, 2026, AND "
    "ENDING SEPTEMBER 30, 2027; AUTHORIZING THE EXECUTIVE DIRECTOR TO SUBMIT SAID PROPOSED MILLAGE RATE OF "
    "0.3800 MILLS AND STATUTORILY DEFINED ROLLED-BACK RATE OF 0.3745 MILLS TO THE MIAMI-DADE COUNTY PROPERTY "
    "APPRAISER AND TAX COLLECTOR TOGETHER WITH THE DATES, TIMES, LOCATIONS, OR…"
)
R0321_SUMMARY = (
    "This resolution authorizes the Downtown Development Authority of the City of Miami to submit a proposed "
    "millage rate to the Miami-Dade County Property Appraiser and Tax Collector. The proposed millage rate is "
    "0.3800 mills, and the authority must also submit a statutorily defined rolled-back rate of 0.3745 mills. "
    "The resolution requires the Executive Director to submit this information along with the dates, times, "
    "and locations of public hearings."
)

R0331_TITLE = (
    "A RESOLUTION OF THE MIAMI CITY COMMISSION AUTHORIZING THE CITY MANAGER TO ACCEPT, IF AWARDED, GRANT "
    "FUNDING IN THE AMOUNT OF SIXTY THOUSAND AND 00/100 DOLLARS ($60,000.00) FROM THE FLORIDA DEPARTMENT OF "
    "ENVIRONMENTAL PROTECTION'S FLORIDA COASTAL MANAGEMENT PROGRAM, THROUGH THE COASTAL PARTNERSHIP INITIATIVE, "
    'FOR THE "VIRGINIA KEY DUNE ECOSYSTEM RESTORATION" PROJECT; AUTHORIZING THE CITY MANAGER TO NEGOTIATE AND '
    "EXECUTE ALL NECESSARY AGREEMENTS, AMENDMENTS, RENEWALS, EXTENSIONS, AND RE…"
)
R0331_SUMMARY = (
    "Miami is authorizing its City Manager to accept grant funding of $60,000 from the Florida Department of "
    "Environmental Protection's Coastal Management Program for the \"Virginia Key Dune Ecosystem Restoration\" "
    "project. The City Manager is also authorized to negotiate and execute agreements related to the project, "
    "and to take all necessary actions to implement it."
)


# --- Open Government Sunset Review bills -------------------------------------------------


def test_sunset_review_bill_is_recognised_from_its_title_or_text():
    assert is_sunset_review("OGSR/Department of Military Affairs", H7019_TEXT)
    assert is_sunset_review("Public Records", H7019_TEXT)  # the act title says so too
    assert not is_sunset_review("Public Assistance", "Section 1. The agency shall seek a waiver.")


def test_sunset_sentence_uses_the_date_as_amended_not_the_struck_one():
    assert sunset_sentence(H7019_TEXT) == "The exemption is repealed on October 2, 2031, unless the Legislature reenacts it."


def test_h7019_inverted_sunset_is_replaced_and_the_rest_is_kept():
    fixed = apply_sunset_rule(H7019_SUMMARY, H7019_TEXT)
    assert "remain in place" not in fixed
    assert fixed.startswith("This bill extends the exemption from public record requirements")
    assert "after making any necessary redactions." in fixed
    assert fixed.endswith("The exemption is repealed on October 2, 2031, unless the Legislature reenacts it.")


def test_two_exemptions_with_different_dates():
    text = H7019_TEXT.replace("Section 2.", (
        "(5) OTHER.—This subsection is subject to the Open Government Sunset Review Act in accordance with "
        "s. 119.15 and shall stand repealed on October 2, 2030, unless reviewed and saved from repeal through "
        "reenactment by the Legislature.\nSection 2."
    ))
    assert sunset_sentence(text) == (
        "The exemptions are repealed on October 2, 2030 and October 2, 2031, unless the Legislature reenacts them."
    )


def test_bill_that_deletes_the_repeal_saves_the_exemption():
    text = H7019_TEXT.replace(
        "This subsection is subject to\nthe Open Government Sunset Review Act in accordance with s.\n"
        "119.15 and shall stand repealed on October 2, [added: 2031] [deleted: 2026,] unless\n"
        "reviewed and saved from repeal through reenactment by the\nLegislature.",
        "[deleted: This subsection is subject to the Open Government Sunset Review Act in accordance with s. "
        "119.15 and shall stand repealed on October 2, 2026, unless reviewed and saved from repeal through "
        "reenactment by the Legislature.]",
    )
    assert sunset_sentence(text) == "The bill removes the scheduled repeal, so the exemption no longer expires."


def test_sunset_rule_leaves_other_bills_alone():
    s = "This bill requires the agency to seek federal approval. It takes effect July 1, 2026."
    assert apply_sunset_rule(s, "Section 1. The agency shall seek approval.") == s


def test_effective_date_sentence_is_not_mistaken_for_the_sunset():
    s = H7019_SUMMARY.replace("The exemption will remain", "The bill takes effect upon becoming law. The exemption will remain")
    fixed = apply_sunset_rule(s, H7019_TEXT)
    assert "takes effect upon becoming law" in fixed
    assert "remain in place" not in fixed


# --- Status words on records that aren't enacted ----------------------------------------


@pytest.mark.parametrize(
    "text,jurisdiction",
    [
        ("The Florida legislature has passed a bill that makes several changes to public assistance.", None),
        ("The Florida Senate has passed a bill that requires an annual study.", None),
        ("Margate has agreed to a contract with the Federation of Public Employees.", "Margate"),
        ("Margate's city government has agreed to work with the MCRA.", "Margate"),
        ("The road is now renamed Jane Doe Way.", None),
        ("The measure has been signed into law.", None),
        ("The City Commission has approved a new budget.", "Miami"),
    ],
)
def test_status_words_are_caught(text, jurisdiction):
    assert overstates_status(text, jurisdiction=jurisdiction)


@pytest.mark.parametrize(
    "text",
    [
        "This bill requires the Agency for Health Care Administration to seek federal approval.",
        "The resolution approves a collective bargaining agreement with the Federation of Public Employees.",
        "Landowners who have approved plans may build without a second review.",  # content, not status
        "A permit that has been approved stays valid for two years.",
        "The bill applies to agreements the county has entered into before July 1.",
        "The fee is now $25 under current law and the bill raises it to $40.",
    ],
)
def test_ordinary_content_is_not_flagged(text):
    assert not overstates_status(text, jurisdiction="Margate")


@pytest.mark.parametrize(
    "status,enacted",
    [
        ("Passed", True), ("Adopted", True), ("Enacted", True), ("Became Law", True),
        ("Adopted with Modification(s)", True), ("Approved with Conditions", True),
        ("Failed", False), ("Introduced", False), ("Agenda Ready", False), ("Engrossed", False),
        ("Passed on First Reading", False), ("Recommended Approval", False), ("Passed Senate", False),
        ("Vetoed", False), ("", False), (None, False),
    ],
)
def test_is_enacted(status, enacted):
    assert is_enacted(status) is enacted


# --- Title-only local items: modality and dropped conditions ----------------------------


def test_requires_where_the_title_authorizes_is_flagged():
    assert overstates_title_modal(R0321_SUMMARY, R0321_TITLE)


def test_authorizes_where_the_title_authorizes_is_fine():
    assert not overstates_title_modal(R0331_SUMMARY, R0331_TITLE)


def test_requires_where_the_title_directs_is_fine():
    title = "A RESOLUTION DIRECTING THE CITY MANAGER TO SUBMIT THE ANNUAL DRAINAGE REPORT TO THE COUNTY ENGINEER BY MARCH 1"
    summary = "The resolution requires the City Manager to submit the annual drainage report to the county engineer by March 1."
    assert not overstates_title_modal(summary, title)


def test_must_on_the_authorized_actor_is_flagged():
    assert overstates_title_modal("The Executive Director must submit the proposed rate to the county.", R0321_TITLE)


def test_authorizing_and_directing_is_a_duty():
    title = "A RESOLUTION AUTHORIZING AND DIRECTING THE CITY MANAGER TO EXECUTE THE AGREEMENT"
    assert not overstates_title_modal("The resolution requires the City Manager to execute the agreement.", title)
    # Miami 19780 puts it the other way round.
    title = "A RESOLUTION OF THE MIAMI CITY COMMISSION DIRECTING AND AUTHORIZING THE CITY MANAGER TO ESTABLISH A NEW SPECIAL REVENUE ACCOUNT"
    assert not overstates_title_modal("The Miami City Commission is directing the city manager to establish a new special revenue account.", title)


# False positives found on the 9,138 title-only items in production (2026-11-27).
def test_code_violation_permit_requirement_is_not_flagged():
    title = (
        "DEL-26-058 A & B Massey Property Address: 2289 Rabenton Road, Deltona, FL 32738 Parcel ID: 8130-58-05-0100 "
        "Property Owner: Salas Antonio Jr Violation: A City of Deltona Ordinance, Section 18-3, adopting the latest "
        "edition of the Florida Building Code, requires a permit to be obtained"
    )
    summary = "The request requires the property owner, Salas Antonio Jr, to obtain a permit before constructing an accessory structure."
    assert not overstates_title_modal(summary, title)


def test_settlement_release_requirement_is_not_flagged():
    title = (
        "A RESOLUTION OF THE MIAMI CITY COMMISSION AUTHORIZING THE DIRECTOR OF FINANCE TO PAY CHARLES STEFFANI, "
        "WITHOUT ADMISSION OF LIABILITY, THE TOTAL SUM OF ONE HUNDRED THOUSAND AND 00/100 DOLLARS ($100,000.00) "
        "UPON THE EXECUTION OF A GENERAL RELEASE"
    )
    summary = (
        "This resolution authorizes the Director of Finance to pay Charles Steffani $100,000 without admitting "
        "liability. The payment requires the claimants to sign a general release of the City."
    )
    assert not overstates_title_modal(summary, title)


@pytest.mark.parametrize("kept", [
    "The item is a request to accept a grant program award, if received, to purchase turnout gear.",
    "The item is a request to accept funding from the Waterways Assistance Program, pending an award.",
])
def test_condition_kept_in_other_words(kept):
    assert not drops_condition(kept, "REQUEST TO ACCEPT, IF AWARDED, GRANT FUNDING FOR TURNOUT GEAR")


def test_three_sunset_dates_read_as_a_list():
    text = H7019_TEXT
    for year in ("2027", "2028"):
        text = text.replace("Section 2.", (
            "(9) X.—This subsection is subject to the Open Government Sunset Review Act in accordance with s. 119.15 "
            f"and shall stand repealed on October 2, {year}, unless reviewed and saved from repeal through "
            "reenactment by the Legislature.\nSection 2."
        ))
    assert sunset_sentence(text) == (
        "The exemptions are repealed on October 2, 2027; October 2, 2028; and October 2, 2031, "
        "unless the Legislature reenacts them."
    )


def test_dropped_if_awarded_is_flagged():
    assert drops_condition(R0331_SUMMARY, R0331_TITLE)


def test_kept_if_awarded_is_fine():
    kept = R0331_SUMMARY.replace("to accept grant funding", "to accept, if awarded, grant funding")
    assert not drops_condition(kept, R0331_TITLE)
    reworded = R0331_SUMMARY.replace("to accept grant funding", "to accept grant funding if the city is awarded it")
    assert not drops_condition(reworded, R0331_TITLE)


def test_no_condition_in_the_source_is_fine():
    assert not drops_condition(R0321_SUMMARY, R0321_TITLE)


def test_subject_to_appropriation_must_be_kept():
    title = "A RESOLUTION AUTHORIZING A $2 MILLION GRANT TO THE ARTS TRUST, SUBJECT TO APPROPRIATION BY THE COMMISSION"
    assert drops_condition("The resolution authorizes a $2 million grant to the Arts Trust.", title)
    assert not drops_condition("The resolution authorizes a $2 million grant to the Arts Trust, subject to appropriation.", title)


# --- Wiring: the generators retry, rewrite or fall back -------------------------------

from datetime import datetime, timezone  # noqa: E402

from app.models import Source  # noqa: E402
from app.pipeline import summarize  # noqa: E402
from app.pipeline.summarize import (  # noqa: E402
    ITEM_FALLBACK_GENERATED_BY,
    check_bill_what_it_does,
    generate_item_description,
    generate_local_legislation_summary,
)

MODEL = "llama3.1:8b"


class SeqClient:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []
        self.model = MODEL

    def generate(self, prompt, **_):
        self.prompts.append(prompt)
        return self.answers.pop(0)


S1758_STATUS = "The Florida legislature has passed a bill that makes several changes to the state's public assistance programs."


def _check(answer, client, *, status="Failed", title="Public Assistance", text="Section 1. The agency shall seek approval.", description="Requiring AHCA to seek federal approval for work requirements"):
    return check_bill_what_it_does(
        answer, bill_number="S1758", title=title, bill_text=text, status=status, description=description, client=client
    )


def test_status_words_on_a_failed_bill_get_one_retry():
    client = SeqClient("This bill makes several changes to the state's public assistance programs.")
    text, fallback = _check(S1758_STATUS, client)
    assert (text, fallback) == ("This bill makes several changes to the state's public assistance programs.", False)
    assert "Never say whether it passed" in client.prompts[0]


def test_a_repeated_status_lead_is_rewritten():
    client = SeqClient("The Florida Senate has passed a bill that requires an annual study of restrictive housing.")
    text, fallback = _check(S1758_STATUS, client)
    assert (text, fallback) == ("This bill requires an annual study of restrictive housing.", False)


def test_status_words_that_cannot_be_rewritten_fall_back_to_the_official_description():
    client = SeqClient("Lawmakers agreed on it. The program is now law.")
    text, fallback = _check(S1758_STATUS, client)
    assert (text, fallback) == ("Requiring AHCA to seek federal approval for work requirements.", True)


def test_an_enacted_bill_is_left_alone():
    client = SeqClient()
    text, fallback = _check(S1758_STATUS, client, status="Passed")
    assert (text, fallback) == (S1758_STATUS, False) and client.prompts == []


def test_the_sunset_rule_runs_for_sunset_review_bills():
    text, fallback = _check(H7019_SUMMARY, SeqClient(), status="Introduced", title="OGSR/Department of Military Affairs", text=H7019_TEXT)
    assert text.endswith("The exemption is repealed on October 2, 2031, unless the Legislature reenacts it.")
    assert "remain in place" not in text and fallback is False


def test_local_resolution_not_adopted_retries_then_falls_back():
    margate = "Margate has agreed to a contract with the Federation of Public Employees for the next three years."
    title = "RESOLUTION - APPROVING COLLECTIVE BARGAINING AGREEMENT WITH THE FEDERATION OF PUBLIC EMPLOYEES"
    ok = "This resolution approves a three-year contract with the Federation of Public Employees."
    text, fallback = generate_local_legislation_summary(
        "ID 2026-319", title, title, item_type="Resolution", jurisdiction="Margate",
        client=SeqClient(margate, ok), enacted=False, title_only=True,
    )
    assert (text, fallback) == (ok, False)
    text, fallback = generate_local_legislation_summary(
        "ID 2026-319", title, title, item_type="Resolution", jurisdiction="Margate",
        client=SeqClient(margate, margate), enacted=False, title_only=True,
    )
    assert fallback is True and text.startswith("Resolution: RESOLUTION - APPROVING")


def test_adopted_local_resolution_may_say_agreed():
    margate = "Margate has agreed to a contract with the Federation of Public Employees."
    text, fallback = generate_local_legislation_summary(
        "ID 2026-235", "T", "T", item_type="Resolution", jurisdiction="Margate",
        client=SeqClient(margate), enacted=True, title_only=True,
    )
    assert (text, fallback) == (margate, False)


def test_title_only_resolution_that_drops_if_awarded_is_retried():
    fixed = R0331_SUMMARY.replace("to accept grant funding", "to accept, if awarded, grant funding")
    client = SeqClient(R0331_SUMMARY, fixed)
    text, fallback = generate_local_legislation_summary(
        "R-26-0331", R0331_TITLE, R0331_TITLE, item_type="Resolution", jurisdiction="Miami",
        client=client, enacted=True, title_only=True,
    )
    assert (text, fallback) == (fixed, False) and len(client.prompts) == 2
    assert 'such as "if awarded"' in client.prompts[1]


def test_title_checks_are_off_when_the_record_has_full_text():
    text, fallback = generate_local_legislation_summary(
        "R-26-0321", R0321_TITLE, "Section 1. The Executive Director shall submit the rate.", item_type="Resolution",
        jurisdiction="Miami", client=SeqClient(R0321_SUMMARY), enacted=True, title_only=False,
    )
    assert (text, fallback) == (R0321_SUMMARY, False)


def test_item_description_gets_the_status_check():
    client = SeqClient("Doral has agreed to work with The Salvation Army.", "The item asks Doral to work with The Salvation Army.")
    text, fallback = generate_item_description(
        "26-9", "AGREEMENT WITH THE SALVATION ARMY", "AGREEMENT WITH THE SALVATION ARMY",
        item_type="Agreement", client=client, enacted=False, jurisdiction="Doral", title_only=True,
    )
    assert (text, fallback) == ("The item asks Doral to work with The Salvation Army.", False)


def _source(db_session, ref):
    src = Source(url="u", document_reference=ref, publisher="p", source_type="legiscan_bill", retrieved_at=datetime.now(timezone.utc))
    db_session.add(src)
    db_session.flush()
    return src


def test_summarize_and_store_applies_the_guards_to_a_failed_state_bill(db_session, bill_factory, monkeypatch):
    e = bill_factory(bill_number="S1758", name="Public Assistance", status="Failed")
    e.bill.full_text = "Section 1. The agency shall seek approval."
    db_session.commit()
    client = SeqClient(S1758_STATUS, "Adult Medicaid recipients.", "This bill requires AHCA to seek federal approval.")
    monkeypatch.setattr(summarize, "OllamaClient", lambda *a, **k: client)
    claims = {c.claim_type: c for c in summarize.summarize_and_store(db_session, e, e.bill.full_text, _source(db_session, "S1758"))}
    assert claims["what_it_does"].claim_text == "This bill requires AHCA to seek federal approval."
    assert claims["what_it_does"].generated_by == f"llm:{MODEL}"


def test_summarize_and_store_marks_a_state_description_fallback_as_rule_made(db_session, bill_factory, monkeypatch):
    e = bill_factory(bill_number="S1758", name="Public Assistance", status="Failed")
    e.bill.full_text = "Section 1. The agency shall seek approval."
    e.bill.description = "Requiring AHCA to seek federal approval"
    db_session.commit()
    client = SeqClient(S1758_STATUS, "Adult Medicaid recipients.", "It has been passed and is now law.")
    monkeypatch.setattr(summarize, "OllamaClient", lambda *a, **k: client)
    claims = {c.claim_type: c for c in summarize.summarize_and_store(db_session, e, e.bill.full_text, _source(db_session, "S1758"))}
    assert claims["what_it_does"].claim_text == "Requiring AHCA to seek federal approval."
    assert claims["what_it_does"].generated_by == ITEM_FALLBACK_GENERATED_BY


# --- Backfill ----------------------------------------------------------------------------

from app.models import Claim  # noqa: E402
from app.pipeline.recheck_summaries import recheck  # noqa: E402


def _claim(db_session, entity, text):
    c = Claim(bill_entity_id=entity.id, claim_type="what_it_does", claim_text=text, generated_by=f"llm:{MODEL}", input_hash="h")
    db_session.add(c)
    db_session.commit()
    return c


def test_recheck_dry_run_changes_nothing(db_session, bill_factory):
    e = bill_factory(bill_number="S1758", status="Failed")
    c = _claim(db_session, e, S1758_STATUS)
    out = recheck(db_session, apply=False)
    assert out.regenerate["status words"] == 1
    db_session.refresh(c)
    assert c.input_hash == "h"


def test_recheck_apply_fixes_sunsets_in_place_and_marks_the_rest(db_session, bill_factory):
    ogsr = bill_factory(bill_number="H7019", name="OGSR/Department of Military Affairs", status="Introduced")
    ogsr.bill.full_text = H7019_TEXT
    failed = bill_factory(bill_number="S1758", status="Failed")
    passed = bill_factory(bill_number="S1000", status="Passed")
    miami = bill_factory(bill_number="R-26-0321", name=R0321_TITLE, status="Adopted")
    miami.jurisdiction_level, miami.jurisdiction_name = "city", "Miami"
    db_session.commit()
    c_ogsr = _claim(db_session, ogsr, H7019_SUMMARY)
    c_failed = _claim(db_session, failed, S1758_STATUS)
    c_passed = _claim(db_session, passed, S1758_STATUS)
    c_miami = _claim(db_session, miami, R0321_SUMMARY)

    out = recheck(db_session, apply=True)

    assert len(out.sunset_fixed) == 1
    assert out.regenerate == {"status words": 1, "authorizes read as requires": 1}
    for c in (c_ogsr, c_failed, c_passed, c_miami):
        db_session.refresh(c)
    assert c_ogsr.claim_text.endswith("unless the Legislature reenacts it.") and c_ogsr.input_hash == "h"
    assert c_failed.input_hash is None and c_miami.input_hash is None
    assert c_passed.input_hash == "h"  # enacted: may say it passed
