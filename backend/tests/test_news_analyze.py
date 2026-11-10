import json

import pytest

from app.news_analysis.analyze import AnalysisError, analyze
from app.news_analysis.schema import Target, validate

TEXT = (
    "The council voted 5-2 to adopt the rental registry. "
    "\"This registry will protect tenants,\" said Councilor Ruiz. "
    "Landlord groups called the fee burdensome."
)
T = Target("b1", "v2")


class Fake:
    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def generate(self, prompt, *, json_mode=False):
        assert json_mode
        self.prompts.append(prompt)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a if isinstance(a, str) else json.dumps(a)


def run(answer, scope="full_text", text=TEXT):
    return analyze(text, article_url="https://e.org/a", text_scope=scope, target=T, bill_name="Rental Registry",
                   bill_summary="Requires landlords to register rentals.", client=Fake(answer), method_version="m1")


GOOD = {
    "tone": {"label": "neutral", "passages": ["The council voted 5-2 to adopt the rental registry."], "rationale": "plain report"},
    "stances": [
        {"speaker_role": "narrator", "speaker_name": None, "label": "descriptive", "passages": ["The council voted 5-2"], "rationale": "reports"},
        {"speaker_role": "quoted_speaker", "speaker_name": "Councilor Ruiz", "label": "supports", "passages": ["This registry will protect tenants"], "rationale": "says it protects tenants"},
    ],
    "arguments": [{"text": "It protects tenants", "quote": "This registry will protect tenants", "speaker_role": "quoted_speaker", "speaker_name": "Councilor Ruiz"}],
}


def test_a_good_answer_becomes_a_valid_analysis_with_offsets_set_by_us():
    a = run(GOOD)
    assert validate(a) == []
    p = a.stances[1].passages[0]
    assert TEXT[p.char_start:p.char_end] == "This registry will protect tenants"
    assert a.model_estimate and a.arguments[0].speaker_name == "Councilor Ruiz"


def test_a_quote_not_in_the_text_is_dropped_and_the_stance_downgraded_not_repaired():
    bad = json.loads(json.dumps(GOOD))
    bad["stances"][1]["passages"] = ["This registry will harm tenants"]  # not in the article
    bad["arguments"][0]["quote"] = "It will protect every tenant"
    a = run(bad)
    quoted = [s for s in a.stances if s.speaker_role == "quoted_speaker"][0]
    assert quoted.label == "insufficient_evidence" and quoted.passages == ()
    assert a.arguments == ()  # an argument with no real quote is not kept


def test_a_stance_without_a_rationale_or_a_quoted_name_is_not_kept_as_a_position():
    ans = {"tone": {"label": "neutral", "passages": ["The council voted 5-2"], "rationale": "x"}, "stances": [
        {"speaker_role": "narrator", "label": "opposes", "passages": ["The council voted 5-2"], "rationale": ""},
        {"speaker_role": "quoted_speaker", "speaker_name": "", "label": "supports", "passages": ["The council"], "rationale": "r"},
    ]}
    a = run(ans)
    assert [(s.speaker_role, s.label) for s in a.stances] == [("narrator", "insufficient_evidence")]


def test_tone_without_a_passage_is_insufficient_and_unknown_labels_are_too():
    a = run({"tone": {"label": "negative", "passages": ["not in the text"], "rationale": "r"},
             "stances": [{"speaker_role": "narrator", "label": "furious", "passages": ["The council"], "rationale": "r"}]})
    assert a.tone.label == "insufficient_evidence"
    assert a.stances[0].label == "insufficient_evidence"


def test_a_headline_only_article_is_capped_at_descriptive_and_yields_no_arguments():
    head = "Council adopts rental registry"
    ans = {"tone": {"label": "neutral", "passages": [], "rationale": "r"},
           "stances": [{"speaker_role": "narrator", "label": "supports", "passages": ["Council adopts"], "rationale": "r"}],
           "arguments": [{"text": "a", "quote": "Council adopts", "speaker_role": "narrator"}]}
    a = run(ans, scope="headline_only", text=head)
    assert a.stances[0].label == "descriptive" and a.arguments == ()
    assert validate(a) == []


def test_bad_json_is_retried_then_fails_clearly_and_a_model_error_is_wrapped():
    c = Fake("not json", "also not json")
    with pytest.raises(AnalysisError, match="JSON"):
        analyze(TEXT, article_url="u", text_scope="full_text", target=T, bill_name="b", bill_summary="s", client=c, method_version="m")
    assert len(c.prompts) == 2
    c2 = Fake("not json", GOOD)
    assert analyze(TEXT, article_url="u", text_scope="full_text", target=T, bill_name="b", bill_summary="s", client=c2, method_version="m")
    with pytest.raises(AnalysisError, match="model call failed"):
        analyze(TEXT, article_url="u", text_scope="full_text", target=T, bill_name="b", bill_summary="s", client=Fake(RuntimeError("down")), method_version="m")


def test_the_prompt_carries_the_rubric_rules_that_matter():
    c = Fake(GOOD)
    analyze(TEXT, article_url="u", text_scope="full_text", target=T, bill_name="Rental Registry", bill_summary="s", client=c, method_version="m")
    p = c.prompts[0]
    assert "A quotation is not the narrator's view" in p and "not opposition" in p and "character for character" in p
