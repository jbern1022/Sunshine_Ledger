from datetime import datetime, timezone

from app.models import Claim, ClaimSource, Source
from app.pipeline.rhetoric_gap import CLAIM_TYPE, generate_rhetoric_gap, rhetoric_gap_and_store


class FakeOllamaClient:
    """Local fake, distinct from test_topic_tagging_ollama's -- this module's
    orchestration layer (rhetoric_gap_and_store) also reads client.model for
    claim attribution, which the classification-only fake doesn't carry."""

    def __init__(self, response: str, *, model: str = "llama3.1:8b"):
        self.response = response
        self.model = model
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


# --- generate_rhetoric_gap (pure function) ----------------------------------


def test_prompt_explains_the_change_markers():
    """full_text carries [deleted: ...]/[added: ...] markers; the prompt must
    say what they mean so the model doesn't read deleted wording as law."""
    client = FakeOllamaClient("NO_GAP")
    generate_rhetoric_gap("HB 1", "Title", "Desc", "An [deleted: old] [added: new] rule.", client=client)
    assert (
        "In the text, [deleted: …] marks wording the bill removes and "
        "[added: …] marks wording it adds." in client.calls[0]
    )



def test_generate_rhetoric_gap_returns_none_for_no_gap_sentinel():
    client = FakeOllamaClient("NO_GAP")
    result = generate_rhetoric_gap("HB 1", "Renames a Bridge", "Renames a bridge.", "Full text.", client=client)
    assert result is None


def test_generate_rhetoric_gap_returns_none_for_empty_response():
    client = FakeOllamaClient("")
    result = generate_rhetoric_gap("HB 1", "Title", "Desc", "Text", client=client)
    assert result is None


def test_generate_rhetoric_gap_returns_the_gap_text_when_flagged():
    gap_text = "The title implies broad protection, but the text narrows an existing tax credit."
    client = FakeOllamaClient(gap_text)
    result = generate_rhetoric_gap("HB 1", "Taxpayer Protection Act", "Protects taxpayers.", "Full text.", client=client)
    assert result == gap_text


def test_generate_rhetoric_gap_truncates_full_text_for_the_prompt():
    client = FakeOllamaClient("NO_GAP")
    long_text = "x" * 20_000
    generate_rhetoric_gap("HB 1", "Title", "Desc", long_text, client=client)
    assert len(client.calls) == 1
    # The prompt shouldn't carry the full 20k chars of bill text verbatim.
    assert len(client.calls[0]) < 20_000


# --- rhetoric_gap_and_store (DB-backed) --------------------------------------


def _make_source(db_session) -> Source:
    source = Source(
        url="https://example.com/bill.pdf",
        source_type="legiscan_bill",
        retrieved_at=datetime.now(timezone.utc),
    )
    db_session.add(source)
    db_session.flush()
    return source


def test_rhetoric_gap_and_store_requires_full_text(db_session, bill_factory):
    entity = bill_factory()  # bill_factory doesn't set full_text
    source = _make_source(db_session)

    result = rhetoric_gap_and_store(db_session, entity, source)

    assert result is None
    assert db_session.query(Claim).count() == 0


def test_rhetoric_gap_and_store_stores_nothing_when_no_gap_found(db_session, bill_factory, monkeypatch):
    entity = bill_factory()
    entity.bill.full_text = "Full legal text with no gap."
    db_session.commit()
    source = _make_source(db_session)

    import app.pipeline.rhetoric_gap as rhetoric_gap_module

    monkeypatch.setattr(rhetoric_gap_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("NO_GAP"))

    result = rhetoric_gap_and_store(db_session, entity, source)

    assert result is None
    assert db_session.query(Claim).count() == 0


def test_rhetoric_gap_and_store_creates_a_claim_when_a_gap_is_found(db_session, bill_factory, monkeypatch):
    entity = bill_factory()
    entity.bill.full_text = "Full legal text with a real gap."
    db_session.commit()
    source = _make_source(db_session)

    gap_text = "The title oversells what the text actually does."
    import app.pipeline.rhetoric_gap as rhetoric_gap_module

    monkeypatch.setattr(rhetoric_gap_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient(gap_text))

    claim = rhetoric_gap_and_store(db_session, entity, source)

    assert claim is not None
    assert claim.claim_type == CLAIM_TYPE
    assert claim.claim_text == gap_text
    assert claim.generated_by.startswith("llm:")

    links = db_session.query(ClaimSource).filter(ClaimSource.claim_id == claim.id).all()
    assert len(links) == 1
    assert links[0].source_id == source.id


def test_rhetoric_gap_and_store_updates_existing_claim_in_place(db_session, bill_factory, monkeypatch):
    """Same rationale as summarize_and_store: flags reference claims with
    ON DELETE CASCADE, so re-running must update, not delete+recreate."""
    entity = bill_factory()
    entity.bill.full_text = "Full legal text."
    db_session.commit()
    source = _make_source(db_session)

    import app.pipeline.rhetoric_gap as rhetoric_gap_module

    monkeypatch.setattr(rhetoric_gap_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("First gap finding."))
    first = rhetoric_gap_and_store(db_session, entity, source)

    monkeypatch.setattr(rhetoric_gap_module, "OllamaClient", lambda *a, **kw: FakeOllamaClient("Updated gap finding."))
    second = rhetoric_gap_and_store(db_session, entity, source)

    assert first.id == second.id
    assert db_session.query(Claim).filter(Claim.claim_type == CLAIM_TYPE).count() == 1
    assert second.claim_text == "Updated gap finding."
