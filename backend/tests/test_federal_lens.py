import json
from datetime import date

import pytest
from sqlalchemy import select

from app.config import settings
from app.federal.bills import upsert_bill
from app.federal.lens_text import build_federal_who, relevant, scope_note, sections, selected_text, windows
from app.impact_lens import guards
from app.impact_lens.selection import served_rows
from app.impact_lens.vocabulary import COMPATIBLE_VERSIONS, REGISTRY, ROLE_LOCATIONS, VOCABULARY_VERSION, is_forbidden
from app.models import BillLayer, BillLayerCriteria, Entity
from app.pipeline.bill_layers_batch import plan_jobs

BILL = """\
SEC. 1. SHORT TITLE.

    This Act may be cited as the Example Act.

SEC. 2. NATIONAL FLOOD INSURANCE PROGRAM.

    The Administrator shall offer flood insurance policyholders a premium rate cap of 18 percent per year, except that the cap does not apply to a second home.

SEC. 3. DEFENSE.

    The Secretary of Defense shall carry out a program at MacDill Air Force Base.

SEC. 4. MEDICARE.

    A Medicare beneficiary may not be charged a copayment for an annual wellness visit under this section.

SEC. 5. SMALL BUSINESS.

    A small employer shall not be required to file the form described in subsection (b).
"""

Q_FLOOD = "The Administrator shall offer flood insurance policyholders a premium rate cap of 18 percent per year, except that the cap does not apply to a second home."
Q_MED = "A Medicare beneficiary may not be charged a copayment for an annual wellness visit under this section."


# --- vocabulary: the three approved categories ------------------------------------------

def test_the_three_roles_are_in_the_vocabulary_with_a_location_kind_and_pass_the_privacy_filter():
    for role in ("flood_insurance_policyholder", "medicare_beneficiary", "small_employer"):
        assert role in REGISTRY["role"].values and role in ROLE_LOCATIONS and not is_forbidden(role)
    assert ROLE_LOCATIONS["flood_insurance_policyholder"] == "property" and ROLE_LOCATIONS["small_employer"] == "business"
    assert VOCABULARY_VERSION == 3 and 2 in COMPATIBLE_VERSIONS


def test_a_group_names_the_specific_role_not_the_general_one_it_also_matches():
    all_roles = list(REGISTRY["role"].values)
    assert guards.supported_roles("Small employers", all_roles) == ["small_employer"]
    assert guards.supported_roles("Flood insurance policyholders", all_roles) == ["flood_insurance_policyholder"]
    assert guards.supported_roles("Medicare enrollees", all_roles) == ["medicare_beneficiary"]
    assert guards.supported_roles("Employers", all_roles) == ["employer"]            # plain employers unchanged
    assert guards.supported_roles("Insured persons", all_roles) == []                  # unchanged: "insured" head noun rule
    assert guards.supported_roles("Beneficiaries", all_roles) == []                    # Medicaid or Social Security: not Medicare
    assert guards.affected_roles("insurers shall tell every Medicare enrollee", all_roles) == ["medicare_beneficiary"]


def test_criteria_mapped_before_the_change_are_still_served_and_newer_rows_win(db_session, bill_factory):
    entity = bill_factory()
    layer = BillLayer(bill_entity_id=entity.id, layer="who_it_affects", origin="sunshine_ledger_ai", version=1,
                      evidence_state="supported", items=[{"group": "Landlords"}], scope_note="", input_hash="h", generated_by="t",
                      method_version="m")
    db_session.add(layer)
    db_session.flush()
    old = BillLayerCriteria(bill_layer_id=layer.id, entry_index=0, vocabulary_version=2, method_version="impact_lens_criteria/9",
                            generated_by="t", criteria={"v": 2})
    db_session.add(old)
    db_session.flush()
    assert served_rows(db_session, layer)[0].criteria == {"v": 2}                     # still exact, still shown
    db_session.add(BillLayerCriteria(bill_layer_id=layer.id, entry_index=0, vocabulary_version=3, method_version="impact_lens_criteria/10",
                                     generated_by="t", criteria={"v": 3}))
    db_session.flush()
    assert served_rows(db_session, layer)[0].criteria == {"v": 3}


# --- reading only the relevant sections --------------------------------------------------

def test_only_sections_naming_a_category_are_read_and_the_note_says_so():
    secs = sections(BILL)
    assert [s.heading for s in secs] == ["SEC. 1", "SEC. 2", "SEC. 3", "SEC. 4", "SEC. 5"]
    picked, total = relevant(BILL)
    assert [s.heading for s in picked] == ["SEC. 2", "SEC. 4", "SEC. 5"] and total == 5
    assert "MacDill" not in selected_text(BILL) and "Medicare beneficiary" in selected_text(BILL)
    note = scope_note(BILL, 1, 1)
    assert note.startswith("Read 3 of 5 sections") and "Medicare" in note and "flood insurance" in note and "not analyzed" in note


def test_long_relevant_sections_are_split_and_windows_respect_the_limit():
    long_section = "SEC. 9. MEDICARE.\n\n" + "\n".join(f"Medicare line {i} " + "x" * 80 for i in range(400))
    wins = windows(long_section, limit=5000)
    assert len(wins) > 3 and all(len(w) <= 5000 for _, w in wins)
    assert "".join(w for _, w in wins).count("Medicare line") == 400


class FakeLlm:
    model = "fake"

    def __init__(self, items):
        self.items = items
        self.prompts = []

    def generate(self, prompt, json_mode=False):
        self.prompts.append(prompt)
        return json.dumps({"items": self.items})


def test_federal_who_keeps_only_verified_quotes_and_names_the_section():
    llm = FakeLlm([
        {"group": "Flood insurance policyholders", "change": "Premium increases are capped at 18 percent a year.",
         "change_kind": "protection", "quote": Q_FLOOD, "conditions": [], "exceptions": []},
        {"group": "Medicare beneficiaries", "change": "Pay no copayment for an annual wellness visit.", "change_kind": "protection",
         "quote": "A Medicare beneficiary shall never pay anything.", "conditions": [], "exceptions": []},   # not in the text
    ])
    result = build_federal_who("H.R. 1", "Example Act", BILL, llm)
    assert result.evidence_state == "supported"
    assert [e["group"] for e in result.items] == ["Flood insurance policyholders"]
    assert result.items[0]["section_ref"] == "SEC. 2" and result.items[0]["restates_existing_law"] is False
    assert result.scope_note.startswith("Read 3 of 5 sections")
    assert any(d.get("group") == "Medicare beneficiaries" for d in result.dropped)
    assert "MacDill" not in llm.prompts[0]                                              # irrelevant sections never reach the model


def test_federal_who_without_a_relevant_section_is_insufficient_evidence_and_asks_no_model():
    llm = FakeLlm([])
    result = build_federal_who("H.R. 2", "Defense", "SEC. 1. DEFENSE.\n\n    The Secretary shall build a hangar.\n", llm)
    assert result.evidence_state == "insufficient_evidence" and llm.prompts == []


# --- planning ------------------------------------------------------------------------------

def test_federal_bills_plan_only_the_who_layer_from_the_relevant_sections(db_session, monkeypatch):
    monkeypatch.setattr(settings, "layers_who_it_affects", True)
    e = upsert_bill(db_session, congress=119, slug="hr", number=1, title="Example Act", delegation=True)
    e.bill.full_text = BILL
    jobs = plan_jobs(db_session, e, "m")
    assert [(j.layer, j.origin) for j in jobs] == [("who_it_affects", "sunshine_ledger_ai")]
    assert "MacDill" not in jobs[0].input_text
    e.bill.full_text = BILL.replace("MacDill Air Force Base", "Eglin Air Force Base")           # an unrelated section changes
    assert plan_jobs(db_session, e, "m")[0].input_hash == jobs[0].input_hash                   # ... so nothing is regenerated
    e.bill.full_text = BILL.replace("18 percent", "20 percent")                                 # a relevant section changes
    assert plan_jobs(db_session, e, "m")[0].input_hash != jobs[0].input_hash


def test_a_federal_bill_with_no_category_section_plans_nothing(db_session, monkeypatch):
    monkeypatch.setattr(settings, "layers_who_it_affects", True)
    e = upsert_bill(db_session, congress=119, slug="hr", number=3, title="Defense", delegation=True)
    e.bill.full_text = "SEC. 1. DEFENSE.\n\n    The Secretary shall build a hangar.\n"
    assert plan_jobs(db_session, e, "m") == []
