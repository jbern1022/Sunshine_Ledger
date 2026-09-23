import json
from datetime import date

from app.models import BillLayer, StaffAnalysis
from app.pipeline.bill_layers_batch import exit_code, plan_jobs, process_bills

BILL_TEXT = "Section 1. Salary payments may be made by direct deposit.\nSection 2. This act shall take effect July 1, 2027.\n"
ANALYSIS = """III. Effect of Proposed Changes:
Section 1 removes the direct deposit requirement.
IV. Constitutional Issues:
None.
V. Fiscal Impact Statement:
A. Tax/Fee Issues:
None.
VI. Technical Deficiencies:
None.
"""


class RoutingClient:
    """Returns a valid payload for whichever prompt it receives."""

    model = "fake:1"

    def generate(self, prompt, *, json_mode=False):
        if "EXACTLY as written" in prompt:
            return json.dumps({"items": [{"section_ref": "Section 2", "quote": "This act shall take effect July 1, 2027."}]})
        if "fiscal impact section" in prompt:
            return json.dumps({"items": [{"text": "Staff found no fiscal impact on taxes or fees."}]})
        if "direct effects" in prompt:
            return json.dumps({"items": [{"text": "Employees may be paid by check.", "section_ref": "Section 1"}]})
        return json.dumps({"items": [{"text": "Removes the direct deposit requirement.", "section_ref": "Section 1"}]})


def _with_text(db, entity):
    entity.bill.full_text = BILL_TEXT
    db.commit()


def _add_analysis(db, entity, supplement_id=1):
    db.add(StaffAnalysis(
        entity_id=entity.id, legiscan_supplement_id=supplement_id, committee="Rules",
        analysis_date=date(2026, 3, 1), source_url="https://flsenate.gov/a.pdf", text=ANALYSIS,
    ))
    db.commit()


def test_plan_without_staff_analysis_has_only_ai_and_bill_text_jobs(db_session, bill_factory):
    entity = bill_factory()
    _with_text(db_session, entity)
    pairs = {(j.layer, j.origin) for j in plan_jobs(db_session, entity, "fake:1")}
    assert pairs == {
        ("bill_says", "bill_text"),
        ("interpretation", "sunshine_ledger_ai"),
        ("expected_effect", "sunshine_ledger_ai"),
    }


def test_plan_with_staff_analysis_adds_staff_jobs(db_session, bill_factory):
    entity = bill_factory()
    _with_text(db_session, entity)
    _add_analysis(db_session, entity)
    pairs = {(j.layer, j.origin) for j in plan_jobs(db_session, entity, "fake:1")}
    assert ("interpretation", "legislative_staff") in pairs
    assert ("expected_effect", "legislative_staff") in pairs


def test_process_writes_all_blocks_then_nothing_on_rerun(db_session, bill_factory):
    entity = bill_factory()
    _with_text(db_session, entity)
    _add_analysis(db_session, entity)
    written, failed = process_bills(db_session, RoutingClient())
    assert (written, failed) == (5, 0)
    assert process_bills(db_session, RoutingClient()) == (0, 0)
    staff = db_session.query(BillLayer).filter_by(origin="legislative_staff", layer="interpretation").one()
    assert staff.scope_note == "Staff analysis, Rules, 2026-03-01"


def test_new_staff_analysis_versions_only_staff_blocks(db_session, bill_factory):
    entity = bill_factory()
    _with_text(db_session, entity)
    _add_analysis(db_session, entity)
    process_bills(db_session, RoutingClient())
    db_session.add(StaffAnalysis(
        entity_id=entity.id, legiscan_supplement_id=2, committee="Appropriations",
        analysis_date=date(2026, 4, 1), source_url="https://flsenate.gov/b.pdf",
        text=ANALYSIS.replace("removes", "eliminates"),
    ))
    db_session.commit()
    written, _ = process_bills(db_session, RoutingClient())
    assert written == 2  # both staff blocks' inputs changed (new label); AI and bill text blocks unchanged
    ai = db_session.query(BillLayer).filter_by(origin="sunshine_ledger_ai", layer="interpretation").all()
    assert len(ai) == 1


def test_max_minutes_zero_processes_nothing(db_session, bill_factory):
    entity = bill_factory()
    _with_text(db_session, entity)
    written, failed = process_bills(db_session, RoutingClient(), max_minutes=0)
    assert (written, failed) == (0, 0)
    assert db_session.query(BillLayer).count() == 0


def test_max_minutes_stops_starting_new_bills_once_budget_elapsed(db_session, bill_factory):
    first = bill_factory(bill_number="HB 1")
    second = bill_factory(bill_number="HB 2")
    _with_text(db_session, first)
    _with_text(db_session, second)

    # Injectable clock: the start-time call and the budget check before
    # bill 1 both return 0 (within budget); every call after (the check
    # before bill 2) returns past the 1-minute budget.
    calls = {"n": 0}

    def fake_clock():
        calls["n"] += 1
        return 0.0 if calls["n"] <= 2 else 120.0

    written, failed = process_bills(db_session, RoutingClient(), max_minutes=1, clock=fake_clock)
    assert failed == 0
    assert written == 3  # only the first bill's three blocks got written
    assert db_session.query(BillLayer).filter_by(bill_entity_id=second.id).count() == 0


def test_one_bad_bill_does_not_stop_the_batch(db_session, bill_factory):
    good = bill_factory(bill_number="HB 1")
    bad = bill_factory(bill_number="HB 2")
    _with_text(db_session, good)
    _with_text(db_session, bad)

    class FlakyClient(RoutingClient):
        def generate(self, prompt, *, json_mode=False):
            if "HB 2" in prompt:
                return "not json"
            return super().generate(prompt, json_mode=json_mode)

    written, failed = process_bills(db_session, FlakyClient())
    assert written == 3 and failed == 1


def test_exit_code_is_nonzero_only_when_everything_failed():
    assert exit_code(written=0, failed=2) == 1
    assert exit_code(written=3, failed=1) == 0
    assert exit_code(written=0, failed=0) == 0
