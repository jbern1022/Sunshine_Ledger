"""D3 (docs/grant-ready/W1_BASELINE_2026-11-25.md): layers for city and county
ordinances were written with state-bill framing. Jacksonville 2026-0851-E (a
SHIP deadline extension for Jacksonville's own appropriation) got an expected
effect about "local governments". Local records now say whose law it is, the
expected-effect guard drops generalizations the text doesn't make, and only
local records re-version: state bills keep identical prompts and hashes.
"""

import json

from app.pipeline import bill_layers as gen
from app.pipeline.bill_layers_batch import plan_jobs

ORDINANCE = (
    "Section 1. Ordinance 2023-335-E, appropriating funds in support of the State Housing Initiatives "
    "Partnership (SHIP) program is hereby amended to extend the deadline to fully expend funds for "
    "completed projects to no later than March 31, 2027.\n"
    "Section 2. This ordinance shall become effective upon signature by the Mayor.\n"
)


class FakeClient:
    model = "fake:1"

    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def generate(self, prompt, *, json_mode=False):
        self.prompts.append(prompt)
        return json.dumps(self.payload)


def _local(db, bill_factory, *, level="city", name="Jacksonville", item_type="Ordinance"):
    e = bill_factory(bill_number="2026-0851-E", name="SHIP deadline extension")
    e.jurisdiction_level = level
    e.jurisdiction_name = name
    e.attributes = {"item_type": item_type}
    e.bill.full_text = ORDINANCE
    e.bill.source_system = "legistar"
    db.commit()
    return e


def test_state_bill_prompt_title_is_unchanged(bill_factory):
    e = bill_factory(name="Direct deposit")
    assert gen.prompt_title(e) == "Direct deposit"


def test_local_prompt_title_names_instrument_and_government(db_session, bill_factory):
    title = gen.prompt_title(_local(db_session, bill_factory))
    assert title.startswith("SHIP deadline extension\n")
    assert "an ordinance of Jacksonville" in title
    assert "not a state bill" in title
    assert '"local governments"' in title


def test_county_resolution_wording(db_session, bill_factory):
    title = gen.prompt_title(_local(db_session, bill_factory, level="county", name="Broward County",
                                    item_type="Resolution"))
    assert "a resolution of Broward County" in title


def test_expected_effect_drops_generalization_for_local_record():
    client = FakeClient({"items": [
        {"text": "The extension may allow local governments more time to use SHIP funds.",
         "section_ref": "Section 1", "assumptions": ["Projects are delayed."]},
        {"text": "It may give local government entities more time.",
         "section_ref": "Section 1", "assumptions": ["x"]},
        {"text": "Jacksonville may have until March 31, 2027 to spend SHIP funds on completed projects.",
         "section_ref": "Section 1", "assumptions": ["Funds remain unspent."]},
    ]})
    result = gen.build_ai_expected_effect("2026-0851-E", "SHIP", ORDINANCE, client,
                                          local_jurisdiction="Jacksonville")
    assert [i["text"] for i in result.items] == [
        "Jacksonville may have until March 31, 2027 to spend SHIP funds on completed projects."
    ]


def test_expected_effect_keeps_phrase_the_text_uses():
    text = ORDINANCE.replace("completed projects", "completed projects of local governments")
    client = FakeClient({"items": [
        {"text": "Local governments may have more time to spend funds.",
         "section_ref": "Section 1", "assumptions": ["x"]},
    ]})
    result = gen.build_ai_expected_effect("X", "T", text, client, local_jurisdiction="Jacksonville")
    assert len(result.items) == 1


def test_state_bill_expected_effect_not_filtered():
    client = FakeClient({"items": [
        {"text": "Cities may have more time to spend funds.", "section_ref": "Section 1", "assumptions": ["x"]},
    ]})
    result = gen.build_ai_expected_effect("HB 1", "T", ORDINANCE, client)
    assert len(result.items) == 1


def test_only_local_records_get_new_hashes(db_session, bill_factory):
    state = bill_factory(bill_number="HB 1")
    state.bill.full_text = ORDINANCE
    db_session.commit()
    from app.pipeline.bill_layers_store import layer_input_hash

    state_jobs = {(j.layer, j.origin): j.input_hash for j in plan_jobs(db_session, state, "m")}
    assert state_jobs[("interpretation", "sunshine_ledger_ai")] == layer_input_hash(
        "interpretation", "sunshine_ledger_ai", ORDINANCE, "m")

    local = _local(db_session, bill_factory)
    local_jobs = {(j.layer, j.origin): j.input_hash for j in plan_jobs(db_session, local, "m")}
    for layer in ("interpretation", "expected_effect"):
        assert local_jobs[(layer, "sunshine_ledger_ai")] != layer_input_hash(
            layer, "sunshine_ledger_ai", ORDINANCE, "m")
    # Bill says quotes the text verbatim; the framing doesn't change it.
    assert local_jobs[("bill_says", "bill_text")] == layer_input_hash("bill_says", "bill_text", ORDINANCE, "m")


def test_who_it_affects_reads_shall_be_authorized_as_a_permission():
    text = ("Section 1. The Mayor, or her designee, and the Corporation Secretary are hereby authorized to "
            "execute and deliver any and all documents necessary to effectuate the purposes of this ordinance.\n")
    client = FakeClient({"items": [{
        "group": "Mayor, or her designee, and the Corporation Secretary",
        "change": "shall be authorized to execute and deliver documents for this ordinance",
        "change_kind": "permission",
        "quote": ("The Mayor, or her designee, and the Corporation Secretary are hereby authorized to execute and "
                  "deliver any and all documents necessary to effectuate the purposes of this ordinance."),
        "conditions": [], "exceptions": [],
    }]})
    result = gen.build_who_it_affects("2026-0851-E", "T", text, client)
    assert [i["text"] for i in result.items] == ["authorized to execute and deliver documents for this ordinance"]


def test_who_it_affects_still_drops_a_real_requirement_the_text_lacks():
    text = "Section 1. The Mayor may sign documents relating to the extension of the deadline for projects.\n"
    client = FakeClient({"items": [{
        "group": "Mayor", "change": "shall sign documents relating to the extension",
        "change_kind": "obligation",
        "quote": "The Mayor may sign documents relating to the extension of the deadline for projects.",
        "conditions": [], "exceptions": [],
    }]})
    assert gen.build_who_it_affects("X", "T", text, client).items == []


class SequenceClient(FakeClient):
    def __init__(self, *payloads):
        super().__init__(None)
        self.payloads = list(payloads)

    def generate(self, prompt, *, json_mode=False):
        self.prompts.append(prompt)
        return json.dumps(self.payloads.pop(0))


def test_local_expected_effect_retries_once_after_generalizing():
    first = {"items": [{"text": "Local government entities may get more time.", "section_ref": "Section 1",
                        "assumptions": ["x"]}]}
    second = {"items": [{"text": "Jacksonville may have until March 31, 2027 to spend these funds.",
                         "section_ref": "Section 1", "assumptions": ["x"]}]}
    client = SequenceClient(first, second)
    result = gen.build_ai_expected_effect("X", "T", ORDINANCE, client, local_jurisdiction="Jacksonville")
    assert [i["text"] for i in result.items] == ["Jacksonville may have until March 31, 2027 to spend these funds."]
    assert len(client.prompts) == 2 and "Jacksonville's alone" in client.prompts[1]


def test_no_retry_for_state_bills_or_kept_answers():
    ok = {"items": [{"text": "Jacksonville may have more time.", "section_ref": "Section 1", "assumptions": ["x"]}]}
    client = SequenceClient(ok)
    gen.build_ai_expected_effect("X", "T", ORDINANCE, client, local_jurisdiction="Jacksonville")
    assert len(client.prompts) == 1
