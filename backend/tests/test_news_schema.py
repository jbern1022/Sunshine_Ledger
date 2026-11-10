from app.news_analysis.schema import Analysis, Argument, Passage, Stance, Target, Tone, validate

TEXT = (
    "The council voted 5-2 to adopt the rental registry. "
    "\"This registry will protect tenants,\" said Councilor Ruiz. "
    "Landlord groups called the fee burdensome."
)
TARGET = Target(bill_entity_id="b1", bill_text_version="v2")


def passage(quote):
    i = TEXT.index(quote)
    return Passage(quote, i, i + len(quote))


def base(**over):
    kw = dict(article_url="https://example.org/a", article_text=TEXT, text_scope="full_text", target=TARGET, method_version="m1")
    kw.update(over)
    return Analysis(**kw)


def test_a_well_formed_analysis_has_no_problems():
    a = base(
        tone=Tone("neutral", (passage("The council voted 5-2 to adopt the rental registry."),), "reports a vote"),
        stances=(
            Stance("narrator", None, "descriptive", (passage("The council voted 5-2"),), "reports without evaluating"),
            Stance("quoted_speaker", "Councilor Ruiz", "supports", (passage("This registry will protect tenants"),), "says it protects tenants"),
        ),
        arguments=(Argument("It protects tenants", passage("This registry will protect tenants"), "quoted_speaker", "Councilor Ruiz"),),
    )
    assert validate(a) == []


def test_a_quote_that_is_not_the_articles_text_is_rejected():
    bad = Passage("This registry will harm tenants", 53, 85)
    a = base(stances=(Stance("quoted_speaker", "Councilor Ruiz", "opposes", (bad,), "x"),))
    assert any("not the article's text" in p for p in validate(a))
    assert any("outside" in p for p in validate(base(stances=(Stance("narrator", None, "descriptive", (Passage("x", 5000, 5001),), "x"),))))


def test_a_stance_needs_a_passage_a_rationale_and_a_named_quoted_speaker():
    assert any("supporting passage" in p for p in validate(base(stances=(Stance("narrator", None, "supports", (), "r"),))))
    assert any("rationale" in p for p in validate(base(stances=(Stance("narrator", None, "supports", (passage("The council"),), ""),))))
    assert any("needs a name" in p for p in validate(base(stances=(Stance("quoted_speaker", None, "supports", (passage("The council"),), "r"),))))
    assert any("no speaker_name" in p for p in validate(base(stances=(Stance("narrator", "Ruiz", "supports", (passage("The council"),), "r"),))))
    assert validate(base(stances=(Stance("narrator", None, "insufficient_evidence"),))) == []


def test_tone_is_separate_from_stance_and_neither_implies_the_other():
    only_tone = base(tone=Tone("negative", (passage("burdensome"),), "word choice"))
    assert validate(only_tone) == []  # a negative tone with no stance claimed is fine
    assert any("supporting passage" in p for p in validate(base(tone=Tone("negative"))))


def test_a_headline_alone_supports_neither_an_opinion_nor_arguments():
    h = base(text_scope="headline_only", article_text="Council adopts rental registry")
    ok = Stance("narrator", None, "descriptive", (Passage("Council adopts", 0, 14),), "reports the action")
    assert validate(Analysis(**{**h.__dict__, "stances": (ok,)})) == []
    bad = Stance("narrator", None, "opposes", (Passage("Council adopts", 0, 14),), "r")
    assert any("headline alone" in p for p in validate(Analysis(**{**h.__dict__, "stances": (bad,)})))
    arg = Argument("a", Passage("Council adopts", 0, 14), "narrator")
    assert any("headline" in p for p in validate(Analysis(**{**h.__dict__, "arguments": (arg,)})))


def test_one_stance_per_speaker_and_unknown_values_are_rejected():
    s = Stance("quoted_speaker", "Councilor Ruiz", "supports", (passage("This registry"),), "r")
    assert any("same speaker" in p for p in validate(base(stances=(s, s))))
    assert any("unknown label" in p for p in validate(base(stances=(Stance("narrator", None, "angry", (), "r"),))))
    assert any("unknown tone" in p for p in validate(base(tone=Tone("furious"))))
    assert any("text_scope" in p for p in validate(base(text_scope="summary")))


def test_it_must_be_marked_a_model_estimate_and_name_its_target_version():
    assert any("model_estimate" in p for p in validate(base(model_estimate=False)))
    assert any("target needs" in p for p in validate(base(target=Target("b1", ""))))


def test_an_abstained_analysis_carries_no_labels():
    assert validate(base(abstained="article behind a paywall")) == []
    assert validate(base(abstained="x", tone=Tone("neutral")))


def test_scoring_reports_coverage_separately_from_accuracy_and_keeps_recall_honest():
    from app.news_analysis.benchmark import cohens_kappa, score

    gold = ["supports", "supports", "opposes", "mixed"]
    pred = ["supports", None, "supports", "insufficient_evidence"]
    r = score(gold, pred)
    assert r.n == 4 and r.answered == 2 and r.coverage == 0.5
    assert r.accuracy_on_answered == 0.5
    assert r.per_label["supports"] == {"precision": 0.5, "recall": 0.5, "support": 2}  # abstention lowers recall
    assert r.per_label["opposes"]["recall"] == 0.0 and r.per_label["opposes"]["precision"] is None
    assert score(["supports"], [None]).accuracy_on_answered is None


def test_kappa():
    from app.news_analysis.benchmark import cohens_kappa

    assert cohens_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert cohens_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0
    assert cohens_kappa(["a", "a"], ["a", "a"]) is None
