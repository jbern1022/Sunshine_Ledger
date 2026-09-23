# Bill Says / Interpretation / Expected Effect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show three separately labeled layers on each bill page (Bill Says, Interpretation, Expected Effect), each with a legislative-staff block and/or a Sunshine Ledger AI block, append-only versions, and human-review labels.

**Architecture:** A new append-only `bill_layers` table (plus `bill_layer_sources` and `bill_layer_reviews`) sits beside the untouched `claims` table. Pure functions extract staff-analysis sections, run the model, and apply code guards (verbatim quotes, section citations, conditional wording). A nightly batch job writes new versions only when inputs change. `GET /bills/{id}` gains a `layers` object that the bill page renders through one label lookup.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL (JSONB), pytest; Ollama via the existing `OllamaClient`; Next.js App Router, React, Tailwind, vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-23-bill-layers-design.md`

## Global Constraints

- Repo: `/Users/joebernal/Documents/Projects/Sunshine Ledger`. Work on branch `feature/bill-layers` created from `gitea/main` (`git fetch gitea && git switch -c feature/bill-layers gitea/main`). Never commit to local `main`. See `docs/RUNBOOK.md` "Branching workflow".
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Current Alembic head is `a7d3f09c4b21`. The new migration's `down_revision` is `a7d3f09c4b21`.
- **Run one backend test file** (Docker Desktop, ephemeral DB, never production):
  ```bash
  docker --context desktop-linux compose -f docker-compose.test.yml run --rm backend-test \
    sh -c "pip install -q -r requirements-dev.txt && pytest tests/<file>.py -v"; \
  docker --context desktop-linux compose -f docker-compose.test.yml down -v
  ```
  **Full backend suite:** `./scripts/run-tests.sh`.
- **Frontend tests:** `cd frontend && npx vitest run <path>`; typecheck `npx tsc --noEmit`. The local `frontend/node_modules` is damaged (missing rollup native binary, duplicate `react 2` type dirs); Task 9 step 1 repairs it with `rm -rf node_modules && npm ci`.
- Layers: `bill_says`, `interpretation`, `expected_effect`. Origins: `bill_text`, `legislative_staff`, `sunshine_ledger_ai`. Allowed (layer, origin) pairs: `bill_says/bill_text`, `interpretation/legislative_staff`, `interpretation/sunshine_ledger_ai`, `expected_effect/legislative_staff`, `expected_effect/sunshine_ledger_ai`.
- Evidence states stored: `supported`, `insufficient_evidence`. "Not yet evaluated" and "No staff analysis published" are never stored.
- Append-only: the pipeline only inserts `bill_layers` rows, plus setting `superseded_at` on the previous current row. Nothing else on an existing row is ever updated. Reviews are rows in `bill_layer_reviews`.
- Exact public copy (verbatim):
  - Section definitions: Bill Says: "The bill's own words." Interpretation: "What the change means." Expected Effect: "What may happen. Forecasts, not established facts, and not legal or financial advice."
  - Badges: "Bill text"; "Legislative staff analysis · <committee>, <date> · condensed by AI"; "Sunshine Ledger analysis · AI-generated".
  - Review labels: "not reviewed by a person"; "reviewed by a person on <date>".
  - Bill Says note: "Quotes checked word for word against the bill text".
  - Empty states: "Not yet evaluated."; "No staff analysis published."; "Insufficient evidence" followed by the scope note.
  - Fallback label: "AI summary of the official description".
  - Truncation note: "Drawn from the first part of a long bill".
- `reviewer` and `note` from reviews never appear in any public API response.
- Model: the quality model `settings.ollama_model` for every layer (never `ollama_model_fast`). Truncation budget: `MAX_BILL_TEXT_CHARS` (12,000) from `app/pipeline/summarize.py`.

## File Structure

Backend:
- Create `backend/app/models/bill_layer.py`: `BillLayer`, `BillLayerSource`, `BillLayerReview`, vocabulary constants.
- Modify `backend/app/models/__init__.py`: export the three models.
- Create `backend/migrations/versions/b3c8e2f41a90_add_bill_layers.py`.
- Create `backend/app/pipeline/bill_layers_text.py`: pure text functions (staff section extraction, quote verification, section and conditional guards). No model, no DB.
- Modify `backend/app/pipeline/summarize.py`: `OllamaClient.generate` gains an optional `json_mode` flag.
- Create `backend/app/pipeline/bill_layers.py`: prompts plus the five `build_*` functions returning `LayerResult`. Model calls only, no DB.
- Create `backend/app/pipeline/bill_layers_store.py`: input hashing and append-only writes.
- Create `backend/app/pipeline/bill_layers_batch.py`: job planning per bill, nightly CLI.
- Create `backend/app/pipeline/review_bill_layers.py`: quality-gate report, no DB writes.
- Create `backend/app/api/bill_layers_admin.py`: review endpoints.
- Modify `backend/app/main.py`: include the admin router.
- Modify `backend/app/schemas/bill.py` and `backend/app/api/bills.py`: `layers` and `has_staff_analysis` on `BillDetail`.
- Tests: `backend/tests/test_bill_layer_model.py`, `test_bill_layers_text.py`, `test_bill_layers_generate.py`, `test_bill_layers_store.py`, `test_bill_layers_batch.py`, `test_bill_layers_admin.py`, `test_bill_layers_api.py`.

Frontend:
- Modify `frontend/lib/types.ts`: layer types on `BillDetail`.
- Create `frontend/lib/layers.ts`: the single label lookup.
- Create `frontend/components/BillLayers.tsx` and `frontend/components/BillLayers.test.tsx`.
- Modify `frontend/app/bills/[id]/page.tsx`: render `BillLayers` when the bill has any layer block.
- Modify `frontend/app/methodology/page.tsx`: new section.

Ops:
- Modify `scripts/run-ingestion.sh`: nightly step. Modify `docs/RUNBOOK.md`: bill layers and review notes.

---

### Task 1: Data model and migration

**Files:**
- Create: `backend/app/models/bill_layer.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/versions/b3c8e2f41a90_add_bill_layers.py`
- Test: `backend/tests/test_bill_layer_model.py`

**Interfaces:**
- Produces: `from app.models import BillLayer, BillLayerSource, BillLayerReview`; constants in `app.models.bill_layer`: `LAYERS`, `ORIGINS`, `ALLOWED_PAIRS: frozenset[tuple[str, str]]`, `EVIDENCE_STATES`.
- `BillLayer` fields: `id, created_at, bill_entity_id, layer, origin, version, superseded_at, evidence_state, scope_note, items (list[dict]), generated_by, method_version, input_hash`, plus relationships `source_links: list[BillLayerSource]` and `reviews: list[BillLayerReview]`.
- `BillLayerReview` fields: `id, created_at, bill_layer_id, decision, reviewer, note`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_bill_layer_model.py`:
```python
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import BillLayer, BillLayerReview


def _layer(entity, **kw):
    defaults = dict(
        bill_entity_id=entity.id,
        layer="interpretation",
        origin="sunshine_ledger_ai",
        version=1,
        evidence_state="supported",
        scope_note="Bill text",
        items=[{"text": "t", "section_ref": "Section 1", "quote": None, "assumptions": [], "affected_groups": []}],
        generated_by="llm:test",
        method_version="interpretation/sunshine_ledger_ai/1",
        input_hash="h1",
    )
    defaults.update(kw)
    return BillLayer(**defaults)


def test_layer_round_trips(db_session, bill_factory):
    entity = bill_factory()
    row = _layer(entity)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    assert row.superseded_at is None
    assert row.items[0]["section_ref"] == "Section 1"


def test_only_one_current_row_per_bill_layer_origin(db_session, bill_factory):
    entity = bill_factory()
    db_session.add(_layer(entity, version=1))
    db_session.commit()
    db_session.add(_layer(entity, version=2, input_hash="h2"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_disallowed_layer_origin_pair_rejected(db_session, bill_factory):
    entity = bill_factory()
    db_session.add(_layer(entity, layer="bill_says", origin="sunshine_ledger_ai"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_review_row_links_to_layer(db_session, bill_factory):
    entity = bill_factory()
    row = _layer(entity)
    db_session.add(row)
    db_session.commit()
    db_session.add(BillLayerReview(bill_layer_id=row.id, decision="approved", reviewer="admin"))
    db_session.commit()
    db_session.refresh(row)
    assert [r.decision for r in row.reviews] == ["approved"]
```

Note: the test DB is built with `Base.metadata.create_all` (see `tests/conftest.py`), so the partial unique index and the CHECK constraint must be declared on the model's `__table_args__`, not only in the migration.

- [ ] **Step 2: Run it and confirm it fails**

Run the one-file command with `tests/test_bill_layer_model.py`. Expected: ImportError, `cannot import name 'BillLayer'`.

- [ ] **Step 3: Write the model**

`backend/app/models/bill_layer.py`:
```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

LAYERS = ("bill_says", "interpretation", "expected_effect")
ORIGINS = ("bill_text", "legislative_staff", "sunshine_ledger_ai")
ALLOWED_PAIRS = frozenset(
    {
        ("bill_says", "bill_text"),
        ("interpretation", "legislative_staff"),
        ("interpretation", "sunshine_ledger_ai"),
        ("expected_effect", "legislative_staff"),
        ("expected_effect", "sunshine_ledger_ai"),
    }
)
EVIDENCE_STATES = ("supported", "insufficient_evidence")

_PAIR_SQL = " OR ".join(f"(layer = '{layer}' AND origin = '{origin}')" for layer, origin in sorted(ALLOWED_PAIRS))


class BillLayer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One version of one block on a bill page: (layer, origin) -- e.g. the
    Sunshine Ledger AI's Interpretation of a bill, version 3.

    Append-only. A changed input inserts version N+1 and stamps
    `superseded_at` on version N; nothing else on a row is ever updated. That
    is what lets the page show earlier versions, and what the Evidence &
    Source Hierarchy doc means by never silently rewriting an interpretation.
    See docs/superpowers/specs/2026-09-23-bill-layers-design.md.

    "Not yet evaluated" is deliberately not a stored state: it is the
    absence of a row. A missing analysis must never read as a finding.
    """

    __tablename__ = "bill_layers"
    __table_args__ = (
        CheckConstraint(_PAIR_SQL, name="ck_bill_layers_allowed_pair"),
        CheckConstraint("evidence_state IN ('supported', 'insufficient_evidence')", name="ck_bill_layers_evidence_state"),
        UniqueConstraint("bill_entity_id", "layer", "origin", "version", name="uq_bill_layers_version"),
        Index(
            "uq_bill_layers_one_current",
            "bill_entity_id",
            "layer",
            "origin",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    layer: Mapped[str] = mapped_column(String(30), nullable=False)
    origin: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_state: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_note: Mapped[str] = mapped_column(Text, nullable=False)
    # [{text, section_ref, quote, assumptions: [], affected_groups: []}]
    items: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    method_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    source_links: Mapped[list["BillLayerSource"]] = relationship(back_populates="bill_layer", cascade="all, delete-orphan")
    reviews: Mapped[list["BillLayerReview"]] = relationship(
        back_populates="bill_layer", cascade="all, delete-orphan", order_by="BillLayerReview.created_at"
    )

    def __repr__(self) -> str:
        return f"<BillLayer {self.layer}/{self.origin} v{self.version} for {self.bill_entity_id}>"


class BillLayerSource(Base):
    """Join table: which Sources back a given BillLayer version."""

    __tablename__ = "bill_layer_sources"

    bill_layer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bill_layers.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )

    bill_layer: Mapped["BillLayer"] = relationship(back_populates="source_links")
    source: Mapped["Source"] = relationship()


class BillLayerReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person's review of one BillLayer version. Append-only, kept apart
    from bill_layers so reviewing never edits the reviewed row.

    `reviewer` and `note` are internal: never returned by a public endpoint.
    """

    __tablename__ = "bill_layer_reviews"
    __table_args__ = (CheckConstraint("decision IN ('approved')", name="ck_bill_layer_reviews_decision"),)

    bill_layer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bill_layers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    bill_layer: Mapped["BillLayer"] = relationship(back_populates="reviews")
```

In `backend/app/models/__init__.py`, add `from app.models.bill_layer import BillLayer, BillLayerReview, BillLayerSource` after the `StaffAnalysis` import, and add `"BillLayer"`, `"BillLayerSource"`, `"BillLayerReview"` to `__all__`.

- [ ] **Step 4: Run the test and confirm it passes**

Same command. Expected: 4 passed.

- [ ] **Step 5: Write the migration**

`backend/migrations/versions/b3c8e2f41a90_add_bill_layers.py`:
```python
"""add bill_layers, bill_layer_sources, bill_layer_reviews

Append-only storage for the Bill Says / Interpretation / Expected Effect
blocks on the bill page, their sources, and human reviews. See
docs/superpowers/specs/2026-09-23-bill-layers-design.md.

Revision ID: b3c8e2f41a90
Revises: a7d3f09c4b21
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b3c8e2f41a90'
down_revision: Union[str, None] = 'a7d3f09c4b21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PAIRS = (
    "(layer = 'bill_says' AND origin = 'bill_text') OR "
    "(layer = 'expected_effect' AND origin = 'legislative_staff') OR "
    "(layer = 'expected_effect' AND origin = 'sunshine_ledger_ai') OR "
    "(layer = 'interpretation' AND origin = 'legislative_staff') OR "
    "(layer = 'interpretation' AND origin = 'sunshine_ledger_ai')"
)


def upgrade() -> None:
    op.create_table(
        'bill_layers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('bill_entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('layer', sa.String(length=30), nullable=False),
        sa.Column('origin', sa.String(length=30), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('evidence_state', sa.String(length=30), nullable=False),
        sa.Column('scope_note', sa.Text(), nullable=False),
        sa.Column('items', postgresql.JSONB(), nullable=False),
        sa.Column('generated_by', sa.String(length=100), nullable=False),
        sa.Column('method_version', sa.String(length=80), nullable=False),
        sa.Column('input_hash', sa.String(length=64), nullable=False),
        sa.CheckConstraint(_PAIRS, name='ck_bill_layers_allowed_pair'),
        sa.CheckConstraint("evidence_state IN ('supported', 'insufficient_evidence')", name='ck_bill_layers_evidence_state'),
        sa.UniqueConstraint('bill_entity_id', 'layer', 'origin', 'version', name='uq_bill_layers_version'),
    )
    op.create_index('ix_bill_layers_bill_entity_id', 'bill_layers', ['bill_entity_id'])
    op.create_index(
        'uq_bill_layers_one_current', 'bill_layers', ['bill_entity_id', 'layer', 'origin'],
        unique=True, postgresql_where=sa.text('superseded_at IS NULL'),
    )
    op.create_table(
        'bill_layer_sources',
        sa.Column('bill_layer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('bill_layers.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sources.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'bill_layer_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('bill_layer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('bill_layers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('reviewer', sa.String(length=100), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.CheckConstraint("decision IN ('approved')", name='ck_bill_layer_reviews_decision'),
    )
    op.create_index('ix_bill_layer_reviews_bill_layer_id', 'bill_layer_reviews', ['bill_layer_id'])


def downgrade() -> None:
    op.drop_index('ix_bill_layer_reviews_bill_layer_id', table_name='bill_layer_reviews')
    op.drop_table('bill_layer_reviews')
    op.drop_table('bill_layer_sources')
    op.drop_index('uq_bill_layers_one_current', table_name='bill_layers')
    op.drop_index('ix_bill_layers_bill_entity_id', table_name='bill_layers')
    op.drop_table('bill_layers')
```

- [ ] **Step 6: Verify the migration upgrades, downgrades and re-upgrades on the test DB**

```bash
docker --context desktop-linux compose -p sl-migtest -f docker-compose.test.yml run --rm --build backend-test \
  sh -c 'sleep 3; alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic current'; \
docker --context desktop-linux compose -p sl-migtest -f docker-compose.test.yml down -v
```
Expected: the last line is `b3c8e2f41a90 (head)`, with no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/bill_layer.py backend/app/models/__init__.py \
  backend/migrations/versions/b3c8e2f41a90_add_bill_layers.py backend/tests/test_bill_layer_model.py
git commit -m "Add append-only bill_layers, sources and reviews tables"
```

---

### Task 2: Pure text functions (staff sections, quote check, guards)

**Files:**
- Create: `backend/app/pipeline/bill_layers_text.py`
- Test: `backend/tests/test_bill_layers_text.py`

**Interfaces:**
- Produces:
  - `normalize_ws(s: str) -> str`
  - `verify_quotes(candidates: list[dict], text: str) -> tuple[list[dict], list[dict]]`: returns (kept, dropped). Each candidate has a `quote` key.
  - `bill_section_numbers(text: str) -> set[str]`: e.g. `{"1", "2"}` from lines starting `Section 1.`
  - `section_number(ref: str | None) -> str | None`: `"Section 3"`, `"Sec. 3"`, `"s. 3"` → `"3"`
  - `is_conditional(statement: str) -> bool`
  - `states_no_or_unknown_impact(statement: str) -> bool`
  - `extract_effect_section(analysis_text: str) -> str | None`
  - `extract_fiscal_section(analysis_text: str) -> str | None`

Heading strings verified against production staff analyses on 2026-09-23 (4,203 of 4,308 analyses match one of the two formats):
- Senate: `III. Effect of Proposed Changes:` … `IV. Constitutional Issues:`; `V. Fiscal Impact Statement:` … `VI. Technical Deficiencies:`.
- House body: `EFFECT OF THE BILL:` … `FISCAL OR ECONOMIC IMPACT:`; `FISCAL OR ECONOMIC IMPACT:` … `RELEVANT INFORMATION`. The House summary box uses mixed-case `Effect of the Bill:` / `Fiscal or Economic Impact:`; the body headings are upper case. Match the body headings case-sensitively. When there's no body fiscal section, fall back to the summary `Fiscal or Economic Impact:` up to `JUMP TO SUMMARY` or a line that is exactly `ANALYSIS`.
- House text contains navigation lines `JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION`; strip them from extracted sections.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_bill_layers_text.py`:
```python
from app.pipeline.bill_layers_text import (
    bill_section_numbers,
    extract_effect_section,
    extract_fiscal_section,
    is_conditional,
    normalize_ws,
    section_number,
    states_no_or_unknown_impact,
    verify_quotes,
)

SENATE = """BILL ANALYSIS AND FISCAL IMPACT STATEMENT
I. Summary:
Short summary.
II. Present Situation:
Current law says X.
III. Effect of Proposed Changes:
Section 1 amends s. 17.11, F.S., to remove references to FLAIR.
Section 2 amends s. 110.113, F.S., by removing the direct deposit requirement.
IV. Constitutional Issues:
A. Municipality/County Mandates Restrictions:
None.
V. Fiscal Impact Statement:
A. Tax/Fee Issues:
None.
B. Private Sector Impact:
Indeterminate.
C. Government Sector Impact:
The department may incur costs to update systems.
VI. Technical Deficiencies:
None.
"""

HOUSE = """FLORIDA HOUSE OF REPRESENTATIVES
SUMMARY
Effect of the Bill:
Summary box effect.
Fiscal or Economic Impact:
Summary box fiscal.
JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION
ANALYSIS
EFFECT OF THE BILL:
The bill requires counties to publish notices online.
JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION
It also repeals s. 50.011, F.S.
FISCAL OR ECONOMIC IMPACT:
STATE GOVERNMENT:
None.
LOCAL GOVERNMENT:
Counties may save publication costs.
PRIVATE SECTOR:
Newspapers may lose notice revenue.
RELEVANT INFORMATION
SUBJECT OVERVIEW:
Background.
"""

HOUSE_SUMMARY_ONLY = """FLORIDA HOUSE OF REPRESENTATIVES
SUMMARY
Effect of the Bill:
Summary box effect.
Fiscal or Economic Impact:
The bill has no fiscal impact on state or local government.
JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION
ANALYSIS
EFFECT OF THE BILL:
Body effect.
RELEVANT INFORMATION
"""

BILL = """Section 1. Subsection (2) of section 110.113, Florida Statutes, is amended to read:
110.113 Pay periods.
(2) Salary payments may be made by direct deposit.
Section 2. This act shall take effect July 1, 2027.
"""


def test_normalize_ws_collapses_runs():
    assert normalize_ws("  a \n\t b  ") == "a b"


def test_verify_quotes_keeps_exact_and_whitespace_variants():
    kept, dropped = verify_quotes(
        [
            {"section_ref": "Section 2", "quote": "This act shall take effect July 1, 2027."},
            {"section_ref": "Section 1", "quote": "(2) Salary payments   may be made\nby direct deposit."},
        ],
        BILL,
    )
    assert len(kept) == 2 and dropped == []


def test_verify_quotes_drops_paraphrase_and_invention():
    kept, dropped = verify_quotes(
        [
            {"section_ref": "Section 2", "quote": "The act takes effect on July 1, 2027."},
            {"section_ref": "Section 9", "quote": "Employers must pay a $500 fee."},
            {"section_ref": "Section 1", "quote": ""},
        ],
        BILL,
    )
    assert kept == [] and len(dropped) == 3


def test_bill_section_numbers():
    assert bill_section_numbers(BILL) == {"1", "2"}


def test_section_number_parses_common_forms():
    assert section_number("Section 3") == "3"
    assert section_number("Sec. 12") == "12"
    assert section_number("section 4, subsection (2)") == "4"
    assert section_number("the whole bill") is None
    assert section_number(None) is None


def test_is_conditional():
    assert is_conditional("Employers may need to update payroll.")
    assert is_conditional("Counties are expected to save money.")
    assert not is_conditional("Employers will need to update payroll.")
    assert not is_conditional("The bill removes the requirement.")


def test_states_no_or_unknown_impact():
    assert states_no_or_unknown_impact("Staff found the private sector impact indeterminate.")
    assert states_no_or_unknown_impact("Staff found no fiscal impact on state government.")
    assert not states_no_or_unknown_impact("Counties save money.")


def test_extract_senate_effect_section():
    section = extract_effect_section(SENATE)
    assert section.startswith("Section 1 amends s. 17.11")
    assert "Constitutional Issues" not in section


def test_extract_house_effect_section_uses_body_and_strips_navigation():
    section = extract_effect_section(HOUSE)
    assert "requires counties to publish notices online" in section
    assert "repeals s. 50.011" in section
    assert "JUMP TO SUMMARY" not in section
    assert "Summary box effect" not in section


def test_extract_senate_fiscal_section():
    section = extract_fiscal_section(SENATE)
    assert "Indeterminate." in section
    assert "may incur costs" in section
    assert "Technical Deficiencies" not in section


def test_extract_house_fiscal_section():
    section = extract_fiscal_section(HOUSE)
    assert "LOCAL GOVERNMENT:" in section and "Newspapers may lose" in section
    assert "SUBJECT OVERVIEW" not in section


def test_extract_house_fiscal_falls_back_to_summary_box():
    assert extract_fiscal_section(HOUSE_SUMMARY_ONLY) == "The bill has no fiscal impact on state or local government."


def test_extract_returns_none_when_absent():
    assert extract_effect_section("Unrelated document text.") is None
    assert extract_fiscal_section("Unrelated document text.") is None
```

- [ ] **Step 2: Run and confirm failure**

One-file command with `tests/test_bill_layers_text.py`. Expected: `ModuleNotFoundError: app.pipeline.bill_layers_text`.

- [ ] **Step 3: Implement**

`backend/app/pipeline/bill_layers_text.py`:
```python
"""Pure text helpers for the bill layers pipeline -- no model, no DB.

Everything the page must be able to trust is enforced here in code rather
than asked of the model in a prompt: a Bill Says quote must appear word for
word in the bill text, a Sunshine Ledger expected effect must cite a bill
section that exists and use conditional wording.

Staff-analysis heading strings were sampled from production on 2026-09-23:
4,203 of 4,308 analyses match either the Senate or the House format below.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_NAV_LINE = re.compile(r"(?m)^\s*JUMP TO SUMMARY ANALYSIS RELEVANT INFORMATION\s*$\n?")
_BILL_SECTION = re.compile(r"(?m)^\s*Section\s+(\d+)\.")
_SECTION_REF = re.compile(r"\b(?:section|sec\.?|s\.)\s*(\d+)\b", re.IGNORECASE)
_CONDITIONAL = re.compile(r"\b(may|might|could|would|(?:is|are) expected to)\b", re.IGNORECASE)
_NO_OR_UNKNOWN = re.compile(r"\b(none|no fiscal impact|no impact|indeterminate|insignificant)\b", re.IGNORECASE)

# (start, end) pairs, tried in order. Patterns are matched per line.
_EFFECT_PATTERNS = [
    (r"^\s*III\.\s*Effect of Proposed Changes:\s*$", r"^\s*IV\.\s*Constitutional Issues:"),
    (r"^\s*EFFECT OF THE BILL:\s*$", r"^\s*(?:FISCAL OR ECONOMIC IMPACT:|RELEVANT INFORMATION)\s*$"),
]
_FISCAL_PATTERNS = [
    (r"^\s*V\.\s*Fiscal Impact Statement:\s*$", r"^\s*VI\.\s*Technical Deficiencies:"),
    (r"^\s*FISCAL OR ECONOMIC IMPACT:\s*$", r"^\s*RELEVANT INFORMATION\s*$"),
    (r"^\s*Fiscal or Economic Impact:\s*$", r"^\s*(?:JUMP TO SUMMARY.*|ANALYSIS)\s*$"),
]


def normalize_ws(s: str) -> str:
    return _WS.sub(" ", s).strip()


def verify_quotes(candidates: list[dict], text: str) -> tuple[list[dict], list[dict]]:
    """Keep only quotes that appear verbatim (modulo whitespace) in `text`.

    `text` must be exactly what the model was shown (the truncated text), so
    a quote from beyond the truncation point is dropped too.
    """
    haystack = normalize_ws(text)
    kept: list[dict] = []
    dropped: list[dict] = []
    for c in candidates:
        quote = normalize_ws(c.get("quote") or "")
        if quote and quote in haystack:
            kept.append({**c, "quote": quote})
        else:
            dropped.append(c)
    return kept, dropped


def bill_section_numbers(text: str) -> set[str]:
    return set(_BILL_SECTION.findall(text))


def section_number(ref: str | None) -> str | None:
    if not ref:
        return None
    m = _SECTION_REF.search(ref)
    return m.group(1) if m else None


def is_conditional(statement: str) -> bool:
    return bool(_CONDITIONAL.search(statement))


def states_no_or_unknown_impact(statement: str) -> bool:
    return bool(_NO_OR_UNKNOWN.search(statement))


def _between(text: str, patterns: list[tuple[str, str]]) -> str | None:
    for start, end in patterns:
        m = re.search(start, text, re.MULTILINE)
        if not m:
            continue
        rest = text[m.end():]
        e = re.search(end, rest, re.MULTILINE)
        body = rest[: e.start()] if e else rest
        body = _NAV_LINE.sub("", body).strip()
        if body:
            return body
    return None


def extract_effect_section(analysis_text: str) -> str | None:
    """Staff's section-by-section account of what the bill changes."""
    return _between(analysis_text, _EFFECT_PATTERNS)


def extract_fiscal_section(analysis_text: str) -> str | None:
    """Staff's fiscal impact statement (state, local, private sector)."""
    return _between(analysis_text, _FISCAL_PATTERNS)
```

- [ ] **Step 4: Run and confirm pass**

Same command. Expected: 13 passed.

- [ ] **Step 5: Production spot-check: deferred to Task 11 step 5**

Don't copy code into the production container during development. After deploy, Task 11 step 5 runs this read-only check:

```bash
docker --context sunshine-vm exec sunshineledger-backend-1 python -c "
from app.db import SessionLocal
from app.models import StaffAnalysis
from app.pipeline.bill_layers_text import extract_effect_section, extract_fiscal_section
db = SessionLocal()
rows = db.query(StaffAnalysis).filter(StaffAnalysis.text.isnot(None)).limit(400).all()
e = sum(1 for r in rows if extract_effect_section(r.text)); f = sum(1 for r in rows if extract_fiscal_section(r.text))
print(f'effect {e}/{len(rows)}  fiscal {f}/{len(rows)}')
"
```
Expected: effect extraction ≥ 90%, fiscal ≥ 85%. If lower, sample the misses, add their heading form to the pattern lists with a test, and redeploy before the quality gate.

- [ ] **Step 6: Commit**

```bash
git add backend/app/pipeline/bill_layers_text.py backend/tests/test_bill_layers_text.py
git commit -m "Add staff-analysis section extraction and bill layer text guards"
```

---

### Task 3: Layer generation (prompts and model calls)

**Files:**
- Modify: `backend/app/pipeline/summarize.py` (`OllamaClient.generate`)
- Create: `backend/app/pipeline/bill_layers.py`
- Test: `backend/tests/test_bill_layers_generate.py`

**Interfaces:**
- Consumes: everything from Task 2; `OllamaClient` and `MAX_BILL_TEXT_CHARS` from `app.pipeline.summarize`.
- Produces:
  - `OllamaClient.generate(prompt: str, *, json_mode: bool = False) -> str`
  - `@dataclass LayerResult: evidence_state: str; scope_note: str; items: list[dict]; dropped: list[dict]`
  - `class LayerGenerationError(RuntimeError)`
  - `METHOD_VERSIONS: dict[tuple[str, str], str]`
  - `build_bill_says(bill_number: str, title: str, full_text: str, client) -> LayerResult`
  - `build_ai_interpretation(bill_number: str, title: str, full_text: str, client) -> LayerResult`
  - `build_ai_expected_effect(bill_number: str, title: str, full_text: str, client) -> LayerResult`
  - `build_staff_interpretation(effect_section: str | None, staff_label: str, client) -> LayerResult`
  - `build_staff_expected_effect(fiscal_section: str | None, staff_label: str, client) -> LayerResult`
  - `staff_label` is the human scope text, e.g. `"Staff analysis, Appropriations Committee, 2026-09-12"`.
- Item shape (every item, all keys present): `{"text": str, "section_ref": str | None, "quote": str | None, "assumptions": list[str], "affected_groups": list[str]}`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_bill_layers_generate.py`:
```python
import json

import pytest

from app.pipeline.bill_layers import (
    LayerGenerationError,
    build_ai_expected_effect,
    build_ai_interpretation,
    build_bill_says,
    build_staff_expected_effect,
    build_staff_interpretation,
)

BILL = """Section 1. Subsection (2) of section 110.113, Florida Statutes, is amended to read:
(2) Salary payments may be made by direct deposit.
Section 2. This act shall take effect July 1, 2027.
"""


class FakeClient:
    model = "fake:1"

    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def generate(self, prompt, *, json_mode=False):
        assert json_mode, "layer prompts must request JSON"
        self.prompts.append(prompt)
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


def test_bill_says_keeps_only_verified_quotes():
    client = FakeClient({"items": [
        {"section_ref": "Section 2", "quote": "This act shall take effect July 1, 2027."},
        {"section_ref": "Section 1", "quote": "Employers must pay a fee."},
    ]})
    r = build_bill_says("HB 1", "Pay", BILL, client)
    assert r.evidence_state == "supported"
    assert [i["quote"] for i in r.items] == ["This act shall take effect July 1, 2027."]
    assert r.items[0]["text"] == r.items[0]["quote"]
    assert len(r.dropped) == 1
    assert r.scope_note == "Bill text"


def test_bill_says_with_no_verified_quotes_is_insufficient():
    client = FakeClient({"items": [{"section_ref": "Section 1", "quote": "Invented."}]})
    r = build_bill_says("HB 1", "Pay", BILL, client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.items == []
    assert r.scope_note == "Quotes could not be verified against the bill text"


def test_bill_says_notes_truncation():
    long_text = BILL + ("x" * 20_000)
    client = FakeClient({"items": [{"section_ref": "Section 2", "quote": "This act shall take effect July 1, 2027."}]})
    r = build_bill_says("HB 1", "Pay", long_text, client)
    assert r.scope_note == "Drawn from the first part of a long bill"


def test_ai_interpretation_normalizes_items():
    client = FakeClient({"items": [
        {"text": "Removes the direct deposit requirement.", "section_ref": "Section 1",
         "assumptions": [], "affected_groups": ["State employees"]},
    ]})
    r = build_ai_interpretation("HB 1", "Pay", BILL, client)
    assert r.evidence_state == "supported"
    assert r.items == [{
        "text": "Removes the direct deposit requirement.", "section_ref": "Section 1", "quote": None,
        "assumptions": ["None identified"], "affected_groups": ["State employees"],
    }]


def test_ai_expected_effect_drops_uncited_and_unconditional():
    client = FakeClient({"items": [
        {"text": "State employees may be paid by paper check.", "section_ref": "Section 1", "assumptions": ["Agencies offer checks"]},
        {"text": "State employees will be paid by paper check.", "section_ref": "Section 1", "assumptions": []},
        {"text": "Banks may lose deposits.", "section_ref": "Section 7", "assumptions": []},
        {"text": "Payroll may change.", "section_ref": None, "assumptions": []},
    ]})
    r = build_ai_expected_effect("HB 1", "Pay", BILL, client)
    assert [i["text"] for i in r.items] == ["State employees may be paid by paper check."]
    assert len(r.dropped) == 3


def test_ai_expected_effect_all_dropped_is_insufficient():
    client = FakeClient({"items": [{"text": "Payroll will change.", "section_ref": "Section 1"}]})
    r = build_ai_expected_effect("HB 1", "Pay", BILL, client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.scope_note == "No effects traceable to a specific bill section"


def test_staff_interpretation_without_section_is_insufficient_and_skips_model():
    client = FakeClient({"items": []})
    r = build_staff_interpretation(None, "Staff analysis, Rules Committee, 2026-03-01", client)
    assert r.evidence_state == "insufficient_evidence"
    assert r.scope_note == "Staff analysis, Rules Committee, 2026-03-01 has no Effect of Proposed Changes section"
    assert client.prompts == []


def test_staff_interpretation_uses_scope_label():
    client = FakeClient({"items": [{"text": "Section 1 removes FLAIR references.", "section_ref": "Section 1"}]})
    r = build_staff_interpretation("Section 1 amends s. 17.11 ...", "Staff analysis, Rules Committee, 2026-03-01", client)
    assert r.evidence_state == "supported"
    assert r.scope_note == "Staff analysis, Rules Committee, 2026-03-01"


def test_staff_expected_effect_keeps_literal_none_and_conditional():
    client = FakeClient({"items": [
        {"text": "Staff found the private sector impact indeterminate.", "section_ref": None},
        {"text": "The department may incur costs to update systems.", "section_ref": None},
        {"text": "The department will save $2 million.", "section_ref": None},
    ]})
    r = build_staff_expected_effect("A. Tax/Fee Issues: None ...", "Staff analysis, Rules Committee, 2026-03-01", client)
    assert [i["text"] for i in r.items] == [
        "Staff found the private sector impact indeterminate.",
        "The department may incur costs to update systems.",
    ]


def test_staff_expected_effect_without_fiscal_section_is_insufficient():
    r = build_staff_expected_effect(None, "Staff analysis, Rules Committee, 2026-03-01", FakeClient({"items": []}))
    assert r.evidence_state == "insufficient_evidence"
    assert r.scope_note == "Staff analysis, Rules Committee, 2026-03-01 has no fiscal impact section"


def test_unparseable_model_output_raises():
    with pytest.raises(LayerGenerationError):
        build_ai_interpretation("HB 1", "Pay", BILL, FakeClient("not json"))
```

- [ ] **Step 2: Run and confirm failure**

One-file command with `tests/test_bill_layers_generate.py`. Expected: `ModuleNotFoundError: app.pipeline.bill_layers`.

- [ ] **Step 3: Add JSON mode to `OllamaClient.generate`**

In `backend/app/pipeline/summarize.py`, replace the `generate` method with:
```python
    def generate(self, prompt: str, *, json_mode: bool = False) -> str:
        # json_mode asks Ollama to constrain output to valid JSON (its
        # `format: "json"` option). The bill layers pipeline needs structured
        # items; the existing summary prompts don't pass it and are unchanged.
        body = {"model": self.model, "prompt": prompt, "stream": False}
        if json_mode:
            body["format"] = "json"
        resp = self._client.post(f"{self.host}/api/generate", json=body)
        resp.raise_for_status()
        data = resp.json()
        if "response" not in data:
            raise OllamaError(f"Unexpected Ollama response: {data}")
        return data["response"].strip()
```

- [ ] **Step 4: Implement `bill_layers.py`**

`backend/app/pipeline/bill_layers.py`:
```python
"""Generate the Bill Says / Interpretation / Expected Effect blocks.

Model calls only, no DB access. Every rule the page depends on is enforced
in code after generation (see bill_layers_text.py), never trusted to the
prompt alone:

- Bill Says quotes must appear word for word in the text shown to the model.
- Sunshine Ledger expected effects must cite a bill section that exists and
  use conditional wording.
- Staff expected effects must use conditional wording or report staff's own
  "none" / "indeterminate" finding.

Design: docs/superpowers/specs/2026-09-23-bill-layers-design.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.pipeline.bill_layers_text import (
    bill_section_numbers,
    is_conditional,
    section_number,
    states_no_or_unknown_impact,
    verify_quotes,
)
from app.pipeline.summarize import MAX_BILL_TEXT_CHARS

# Bump a value when its prompt or guard changes in a way that should
# regenerate stored versions. Part of each block's input hash.
METHOD_VERSIONS: dict[tuple[str, str], str] = {
    ("bill_says", "bill_text"): "bill_says/bill_text/1",
    ("interpretation", "legislative_staff"): "interpretation/legislative_staff/1",
    ("interpretation", "sunshine_ledger_ai"): "interpretation/sunshine_ledger_ai/1",
    ("expected_effect", "legislative_staff"): "expected_effect/legislative_staff/1",
    ("expected_effect", "sunshine_ledger_ai"): "expected_effect/sunshine_ledger_ai/1",
}

MAX_STAFF_SECTION_CHARS = 8_000


class LayerGenerationError(RuntimeError):
    pass


@dataclass
class LayerResult:
    evidence_state: str
    scope_note: str
    items: list[dict]
    dropped: list[dict] = field(default_factory=list)


BILL_SAYS_PROMPT = """You are selecting the most important provisions of a bill, quoted exactly, for a civic transparency website.

Bill: {bill_number} — {title}

Bill text:
\"\"\"
{text}
\"\"\"

Pick the 2 to 4 provisions that most change what the law requires, allows, funds, or prohibits. For each, copy one sentence or clause EXACTLY as written above -- character for character, no paraphrasing, no ellipses, no added words. Give the bill section it comes from (e.g. "Section 2").

Respond with JSON only: {{"items": [{{"section_ref": "Section N", "quote": "exact text"}}]}}"""

AI_INTERPRETATION_PROMPT = """You are explaining what a bill changes, for a general public audience with no legal background.

Bill: {bill_number} — {title}

Bill text:
\"\"\"
{text}
\"\"\"

Write 2 to 5 plain-language statements of what this bill changes in the law. Rules:
- Each statement must be tied to the bill section it comes from (e.g. "Section 3").
- Only state what the text supports. Do not speculate about intent, motive, or politics.
- No words implying a value judgment (e.g. "harmful", "beneficial", "important").
- For each statement list the assumptions your reading depends on -- what would have to be true for the statement to hold. If there are none, use an empty list.
- List affected groups ONLY if the text names them; otherwise an empty list.

Respond with JSON only: {{"items": [{{"text": "...", "section_ref": "Section N", "assumptions": ["..."], "affected_groups": ["..."]}}]}}"""

AI_EXPECTED_EFFECT_PROMPT = """You are describing possible direct effects of a bill, for a civic transparency website.

Bill: {bill_number} — {title}

Bill text:
\"\"\"
{text}
\"\"\"

Describe up to 4 direct effects that follow from a specific mechanism in this bill (a requirement, prohibition, funding change, deadline, or penalty it creates or removes). Rules:
- Each effect MUST cite the bill section that creates the mechanism (e.g. "Section 3").
- Use conditional wording: "may", "could", or "is expected to". Never state an effect as certain.
- Do not predict wider economic, social, or behavioral consequences beyond the direct mechanism.
- For each effect list the assumptions it depends on.
- List affected groups ONLY if the text names them.
- If no effect can be tied to a specific section, return an empty list.

Respond with JSON only: {{"items": [{{"text": "...", "section_ref": "Section N", "assumptions": ["..."], "affected_groups": ["..."]}}]}}"""

STAFF_INTERPRETATION_PROMPT = """Below is the "effect of the bill" section of a nonpartisan Florida legislative staff analysis.

\"\"\"
{text}
\"\"\"

Condense it into 2 to 5 plain-language statements of what staff say the bill changes. Rules:
- Restate staff's reading only. Add nothing that is not in the text above.
- Tie each statement to the bill section staff refer to (e.g. "Section 3"), or null if staff don't name one.
- List affected groups only if staff name them.

Respond with JSON only: {{"items": [{{"text": "...", "section_ref": "Section N or null", "affected_groups": ["..."]}}]}}"""

STAFF_EXPECTED_EFFECT_PROMPT = """Below is the fiscal impact section of a nonpartisan Florida legislative staff analysis.

\"\"\"
{text}
\"\"\"

Restate each fiscal finding (tax/fee, private sector, state government, local government) as one plain-language statement. Rules:
- Use conditional wording ("may", "could", "is expected to") for any projected effect.
- If staff say "None", "Indeterminate", or "Insignificant", say so literally, e.g. "Staff found the private sector impact indeterminate." Do not guess.
- List any assumptions staff state. Add nothing that is not in the text above.

Respond with JSON only: {{"items": [{{"text": "...", "assumptions": ["..."]}}]}}"""


def _parse_items(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LayerGenerationError(f"model returned invalid JSON: {raw[:200]!r}") from exc
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise LayerGenerationError(f"model JSON has no items list: {raw[:200]!r}")
    return [i for i in items if isinstance(i, dict)]


def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _item(raw: dict, *, quote: str | None = None, assumptions_required: bool = False) -> dict:
    assumptions = _str_list(raw.get("assumptions"))
    if assumptions_required and not assumptions:
        assumptions = ["None identified"]
    ref = raw.get("section_ref")
    return {
        "text": str(raw.get("text") or quote or "").strip(),
        "section_ref": str(ref).strip() if ref not in (None, "", "null") else None,
        "quote": quote,
        "assumptions": assumptions,
        "affected_groups": _str_list(raw.get("affected_groups")),
    }


def _truncate(full_text: str) -> tuple[str, bool]:
    return full_text[:MAX_BILL_TEXT_CHARS], len(full_text) > MAX_BILL_TEXT_CHARS


def build_bill_says(bill_number: str, title: str, full_text: str, client) -> LayerResult:
    text, truncated = _truncate(full_text)
    raw = _parse_items(client.generate(
        BILL_SAYS_PROMPT.format(bill_number=bill_number, title=title, text=text), json_mode=True
    ))
    kept, dropped = verify_quotes(raw, text)
    if not kept:
        return LayerResult("insufficient_evidence", "Quotes could not be verified against the bill text", [], dropped)
    items = [_item(k, quote=k["quote"]) for k in kept[:4]]
    for i in items:
        i["text"] = i["quote"]
    scope = "Drawn from the first part of a long bill" if truncated else "Bill text"
    return LayerResult("supported", scope, items, dropped)


def build_ai_interpretation(bill_number: str, title: str, full_text: str, client) -> LayerResult:
    text, truncated = _truncate(full_text)
    raw = _parse_items(client.generate(
        AI_INTERPRETATION_PROMPT.format(bill_number=bill_number, title=title, text=text), json_mode=True
    ))
    items = [_item(r, assumptions_required=True) for r in raw if str(r.get("text") or "").strip()][:5]
    scope = "Drawn from the first part of a long bill" if truncated else "Bill text"
    if not items:
        return LayerResult("insufficient_evidence", "No interpretation could be drawn from the bill text", [], raw)
    return LayerResult("supported", scope, items)


def build_ai_expected_effect(bill_number: str, title: str, full_text: str, client) -> LayerResult:
    text, truncated = _truncate(full_text)
    raw = _parse_items(client.generate(
        AI_EXPECTED_EFFECT_PROMPT.format(bill_number=bill_number, title=title, text=text), json_mode=True
    ))
    sections = bill_section_numbers(text)
    kept: list[dict] = []
    dropped: list[dict] = []
    for r in raw:
        item = _item(r, assumptions_required=True)
        if item["text"] and section_number(item["section_ref"]) in sections and is_conditional(item["text"]):
            kept.append(item)
        else:
            dropped.append(r)
    if not kept:
        return LayerResult("insufficient_evidence", "No effects traceable to a specific bill section", [], dropped)
    scope = "Drawn from the first part of a long bill" if truncated else "Bill text"
    return LayerResult("supported", scope, kept[:4], dropped)


def build_staff_interpretation(effect_section: str | None, staff_label: str, client) -> LayerResult:
    if not effect_section:
        return LayerResult("insufficient_evidence", f"{staff_label} has no Effect of Proposed Changes section", [])
    raw = _parse_items(client.generate(
        STAFF_INTERPRETATION_PROMPT.format(text=effect_section[:MAX_STAFF_SECTION_CHARS]), json_mode=True
    ))
    items = [_item(r) for r in raw if str(r.get("text") or "").strip()][:5]
    if not items:
        return LayerResult("insufficient_evidence", f"{staff_label}: nothing could be condensed", [], raw)
    return LayerResult("supported", staff_label, items)


def build_staff_expected_effect(fiscal_section: str | None, staff_label: str, client) -> LayerResult:
    if not fiscal_section:
        return LayerResult("insufficient_evidence", f"{staff_label} has no fiscal impact section", [])
    raw = _parse_items(client.generate(
        STAFF_EXPECTED_EFFECT_PROMPT.format(text=fiscal_section[:MAX_STAFF_SECTION_CHARS]), json_mode=True
    ))
    kept: list[dict] = []
    dropped: list[dict] = []
    for r in raw:
        item = _item(r)
        if item["text"] and (is_conditional(item["text"]) or states_no_or_unknown_impact(item["text"])):
            kept.append(item)
        else:
            dropped.append(r)
    if not kept:
        return LayerResult("insufficient_evidence", f"{staff_label}: no fiscal finding could be restated", [], dropped)
    return LayerResult("supported", staff_label, kept, dropped)
```

- [ ] **Step 5: Run and confirm pass**

Same command, then `tests/test_summarize*.py` and `tests/test_rhetoric_gap.py` to confirm the `generate` change didn't break the existing callers. Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/pipeline/summarize.py backend/app/pipeline/bill_layers.py backend/tests/test_bill_layers_generate.py
git commit -m "Generate bill layer blocks with code-enforced quote, citation and wording guards"
```

---

### Task 4: Append-only store

**Files:**
- Create: `backend/app/pipeline/bill_layers_store.py`
- Test: `backend/tests/test_bill_layers_store.py`

**Interfaces:**
- Consumes: `BillLayer`, `BillLayerSource`, `ALLOWED_PAIRS` (Task 1); `LayerResult`, `METHOD_VERSIONS` (Task 3); `Source` model.
- Produces:
  - `layer_input_hash(layer: str, origin: str, input_text: str, model: str) -> str`
  - `current_layer(db, bill_entity_id, layer: str, origin: str) -> BillLayer | None`
  - `store_layer_version(db, *, bill_entity_id, layer: str, origin: str, result: LayerResult, input_hash: str, generated_by: str, sources: list[Source]) -> BillLayer | None`: returns None (writes nothing) when the current row already has `input_hash`. Commits.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_bill_layers_store.py`:
```python
from datetime import datetime, timezone

import pytest

from app.models import BillLayer, Source
from app.pipeline.bill_layers import LayerResult
from app.pipeline.bill_layers_store import current_layer, layer_input_hash, store_layer_version


def _src():
    return Source(url="https://example.com/bill", source_type="legiscan_bill_text", retrieved_at=datetime.now(timezone.utc))


def _result(text="Removes the requirement."):
    return LayerResult("supported", "Bill text", [{"text": text, "section_ref": "Section 1", "quote": None, "assumptions": [], "affected_groups": []}])


def _store(db, entity, h, text="Removes the requirement."):
    return store_layer_version(
        db, bill_entity_id=entity.id, layer="interpretation", origin="sunshine_ledger_ai",
        result=_result(text), input_hash=h, generated_by="llm:test", sources=[_src()],
    )


def test_hash_depends_on_every_input():
    base = layer_input_hash("interpretation", "sunshine_ledger_ai", "text", "m1")
    assert base != layer_input_hash("interpretation", "sunshine_ledger_ai", "text2", "m1")
    assert base != layer_input_hash("interpretation", "sunshine_ledger_ai", "text", "m2")
    assert base != layer_input_hash("interpretation", "legislative_staff", "text", "m1")


def test_first_store_creates_version_1_with_sources(db_session, bill_factory):
    entity = bill_factory()
    row = _store(db_session, entity, "h1")
    assert row.version == 1 and row.superseded_at is None
    assert row.method_version == "interpretation/sunshine_ledger_ai/1"
    assert len(row.source_links) == 1


def test_unchanged_input_writes_nothing(db_session, bill_factory):
    entity = bill_factory()
    _store(db_session, entity, "h1")
    assert _store(db_session, entity, "h1") is None
    assert db_session.query(BillLayer).count() == 1


def test_changed_input_supersedes_and_preserves_old_text(db_session, bill_factory):
    entity = bill_factory()
    v1 = _store(db_session, entity, "h1", text="Old reading.")
    v2 = _store(db_session, entity, "h2", text="New reading.")
    db_session.refresh(v1)
    assert v2.version == 2 and v2.superseded_at is None
    assert v1.superseded_at is not None
    assert v1.items[0]["text"] == "Old reading."
    assert current_layer(db_session, entity.id, "interpretation", "sunshine_ledger_ai").id == v2.id


def test_disallowed_pair_raises(db_session, bill_factory):
    entity = bill_factory()
    with pytest.raises(ValueError):
        store_layer_version(
            db_session, bill_entity_id=entity.id, layer="bill_says", origin="legislative_staff",
            result=_result(), input_hash="h", generated_by="llm:test", sources=[],
        )
```

- [ ] **Step 2: Run and confirm failure**

One-file command with `tests/test_bill_layers_store.py`. Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`backend/app/pipeline/bill_layers_store.py`:
```python
"""Append-only writes for bill layers.

The only two writes this module ever makes: insert a new version, and stamp
`superseded_at` on the version it replaces -- in one transaction, so the
one-current-row index is never violated mid-way. Nothing else on an
existing row is updated; that is how earlier versions stay intact.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BillLayer, BillLayerSource, Source
from app.models.bill_layer import ALLOWED_PAIRS
from app.pipeline.bill_layers import METHOD_VERSIONS, LayerResult


def layer_input_hash(layer: str, origin: str, input_text: str, model: str) -> str:
    parts = [METHOD_VERSIONS[(layer, origin)], model, input_text]
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def current_layer(db: Session, bill_entity_id: uuid.UUID, layer: str, origin: str) -> BillLayer | None:
    return db.execute(
        select(BillLayer).where(
            BillLayer.bill_entity_id == bill_entity_id,
            BillLayer.layer == layer,
            BillLayer.origin == origin,
            BillLayer.superseded_at.is_(None),
        )
    ).scalar_one_or_none()


def store_layer_version(
    db: Session,
    *,
    bill_entity_id: uuid.UUID,
    layer: str,
    origin: str,
    result: LayerResult,
    input_hash: str,
    generated_by: str,
    sources: list[Source],
) -> BillLayer | None:
    if (layer, origin) not in ALLOWED_PAIRS:
        raise ValueError(f"({layer}, {origin}) is not an allowed layer/origin pair")

    existing = current_layer(db, bill_entity_id, layer, origin)
    if existing is not None and existing.input_hash == input_hash:
        return None

    last_version = db.execute(
        select(func.max(BillLayer.version)).where(
            BillLayer.bill_entity_id == bill_entity_id, BillLayer.layer == layer, BillLayer.origin == origin
        )
    ).scalar() or 0

    if existing is not None:
        existing.superseded_at = datetime.now(timezone.utc)
        db.flush()  # free the one-current-row slot before inserting

    row = BillLayer(
        bill_entity_id=bill_entity_id,
        layer=layer,
        origin=origin,
        version=last_version + 1,
        evidence_state=result.evidence_state,
        scope_note=result.scope_note,
        items=result.items,
        generated_by=generated_by,
        method_version=METHOD_VERSIONS[(layer, origin)],
        input_hash=input_hash,
    )
    db.add(row)
    for source in sources:
        db.add(source)
    db.flush()
    for source in sources:
        db.add(BillLayerSource(bill_layer_id=row.id, source_id=source.id))
    db.commit()
    db.refresh(row)
    return row
```

- [ ] **Step 4: Run and confirm pass**

Same command. Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/bill_layers_store.py backend/tests/test_bill_layers_store.py
git commit -m "Add append-only bill layer version store"
```

---

### Task 5: Batch job and nightly step

**Files:**
- Create: `backend/app/pipeline/bill_layers_batch.py`
- Test: `backend/tests/test_bill_layers_batch.py`
- Modify: `scripts/run-ingestion.sh`

**Interfaces:**
- Consumes: Tasks 2–4; `Bill`, `Entity`, `StaffAnalysis`, `Source` models; `OllamaClient`.
- Produces:
  - `@dataclass LayerJob: layer: str; origin: str; input_text: str; input_hash: str`
  - `latest_staff_analysis(db, entity_id) -> StaffAnalysis | None`: latest by `analysis_date` (nulls last), then `created_at`, with non-empty `text`.
  - `staff_label(analysis: StaffAnalysis) -> str`: `"Staff analysis, <committee or 'committee not stated'>, <YYYY-MM-DD or 'undated'>"`
  - `plan_jobs(db, entity: Entity, model: str) -> list[LayerJob]`: only jobs whose hash differs from the current row.
  - `run_job(db, entity, job, client, analysis) -> BillLayer | None`
  - `process_bills(db, client, *, limit: int | None = None) -> tuple[int, int]`: returns (written, failed).
  - CLI: `python -m app.pipeline.bill_layers_batch [--limit N] [--dry-run]`. `--dry-run` prints planned jobs without calling the model.

Input text per job (and hashed):
- `bill_says/bill_text`, `interpretation/sunshine_ledger_ai`, `expected_effect/sunshine_ledger_ai`: `bill.full_text` (only when non-empty).
- `interpretation/legislative_staff`: the `extract_effect_section(...)` output, or `"<no section>|<analysis id>"` when absent, so the "insufficient" version is still written once and re-evaluated when a new analysis arrives.
- `expected_effect/legislative_staff`: the same with `extract_fiscal_section`.
- No staff jobs when the bill has no staff analysis.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_bill_layers_batch.py`:
```python
import json
from datetime import date

from app.models import BillLayer, StaffAnalysis
from app.pipeline.bill_layers_batch import plan_jobs, process_bills

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
```

- [ ] **Step 2: Run and confirm failure**

One-file command with `tests/test_bill_layers_batch.py`. Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`backend/app/pipeline/bill_layers_batch.py`:
```python
"""Nightly job: write new Bill Says / Interpretation / Expected Effect
versions for bills whose inputs changed.

Per bill, up to five blocks. A block is regenerated only when its input
hash (input text + model + method version) differs from the current
version's, so a new committee staff analysis re-versions the staff blocks
and leaves the Sunshine Ledger blocks alone, and vice versa.

One bill's failure (bad model JSON, Ollama hiccup) is counted and the batch
moves on -- same isolation rule as summarize_batch.

Usage:
    python -m app.pipeline.bill_layers_batch [--limit N] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import Bill, Entity, Source, StaffAnalysis
from app.pipeline import bill_layers as gen
from app.pipeline.bill_layers_store import current_layer, layer_input_hash, store_layer_version
from app.pipeline.bill_layers_text import extract_effect_section, extract_fiscal_section
from app.pipeline.summarize import OllamaClient

logger = logging.getLogger(__name__)


@dataclass
class LayerJob:
    layer: str
    origin: str
    input_text: str
    input_hash: str


def latest_staff_analysis(db: Session, entity_id) -> StaffAnalysis | None:
    return db.execute(
        select(StaffAnalysis)
        .where(StaffAnalysis.entity_id == entity_id, StaffAnalysis.text.isnot(None), StaffAnalysis.text != "")
        .order_by(StaffAnalysis.analysis_date.desc().nulls_last(), StaffAnalysis.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def staff_label(analysis: StaffAnalysis) -> str:
    committee = analysis.committee or "committee not stated"
    when = analysis.analysis_date.isoformat() if analysis.analysis_date else "undated"
    return f"Staff analysis, {committee}, {when}"


def _staff_input(section: str | None, analysis: StaffAnalysis) -> str:
    # The label is part of the input so a newer analysis re-versions the
    # block even when the extracted text is identical: its scope changed.
    return f"{staff_label(analysis)}\n{section if section else f'<no section>|{analysis.id}'}"


def plan_jobs(db: Session, entity: Entity, model: str) -> list[LayerJob]:
    bill = entity.bill
    candidates: list[tuple[str, str, str]] = []
    if bill.full_text:
        for layer, origin in (
            ("bill_says", "bill_text"),
            ("interpretation", "sunshine_ledger_ai"),
            ("expected_effect", "sunshine_ledger_ai"),
        ):
            candidates.append((layer, origin, bill.full_text))
    analysis = latest_staff_analysis(db, entity.id)
    if analysis is not None:
        candidates.append(("interpretation", "legislative_staff", _staff_input(extract_effect_section(analysis.text), analysis)))
        candidates.append(("expected_effect", "legislative_staff", _staff_input(extract_fiscal_section(analysis.text), analysis)))

    jobs: list[LayerJob] = []
    for layer, origin, text in candidates:
        h = layer_input_hash(layer, origin, text, model)
        current = current_layer(db, entity.id, layer, origin)
        if current is None or current.input_hash != h:
            jobs.append(LayerJob(layer, origin, text, h))
    return jobs


def _sources_for(entity: Entity, job: LayerJob, analysis: StaffAnalysis | None) -> list[Source]:
    now = datetime.now(timezone.utc)
    bill = entity.bill
    if job.origin == "legislative_staff" and analysis is not None:
        return [Source(
            url=analysis.source_url,
            document_reference=analysis.committee,
            publisher="Florida Legislature staff",
            source_type="fl_staff_analysis",
            retrieved_at=now,
            metadata_json={"analysis_date": analysis.analysis_date.isoformat() if analysis.analysis_date else None,
                           "used_for": f"bill_layer:{job.layer}"},
        )]
    return [Source(
        url=bill.full_text_url or "",
        document_reference=bill.bill_number,
        publisher=f"{entity.jurisdiction_name or ''} via {bill.source_system}".strip(),
        source_type=f"{bill.source_system}_bill_text",
        retrieved_at=now,
        metadata_json={"used_for": f"bill_layer:{job.layer}"},
    )]


def run_job(db: Session, entity: Entity, job: LayerJob, client, analysis: StaffAnalysis | None):
    bill = entity.bill
    if (job.layer, job.origin) == ("bill_says", "bill_text"):
        result = gen.build_bill_says(bill.bill_number, entity.name, bill.full_text, client)
    elif (job.layer, job.origin) == ("interpretation", "sunshine_ledger_ai"):
        result = gen.build_ai_interpretation(bill.bill_number, entity.name, bill.full_text, client)
    elif (job.layer, job.origin) == ("expected_effect", "sunshine_ledger_ai"):
        result = gen.build_ai_expected_effect(bill.bill_number, entity.name, bill.full_text, client)
    elif (job.layer, job.origin) == ("interpretation", "legislative_staff"):
        result = gen.build_staff_interpretation(extract_effect_section(analysis.text), staff_label(analysis), client)
    else:
        result = gen.build_staff_expected_effect(extract_fiscal_section(analysis.text), staff_label(analysis), client)
    for d in result.dropped:
        logger.info("%s %s/%s dropped item: %s", bill.bill_number, job.layer, job.origin, d)
    return store_layer_version(
        db, bill_entity_id=entity.id, layer=job.layer, origin=job.origin, result=result,
        input_hash=job.input_hash, generated_by=f"llm:{client.model}",
        sources=_sources_for(entity, job, analysis),
    )


def _bills(db: Session) -> list[Entity]:
    return list(db.execute(
        select(Entity).join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill").options(selectinload(Entity.bill))
        .order_by(Bill.last_action_date.desc().nulls_last())
    ).scalars().all())


def process_bills(db: Session, client, *, limit: int | None = None) -> tuple[int, int]:
    """Returns (block versions written, bills failed). `limit` caps bills
    that have work, not bills scanned."""
    written = failed = processed = 0
    for entity in _bills(db):
        if not entity.bill:
            continue
        jobs = plan_jobs(db, entity, client.model)
        if not jobs:
            continue
        if limit is not None and processed >= limit:
            break
        processed += 1
        analysis = latest_staff_analysis(db, entity.id)
        try:
            for job in jobs:
                if run_job(db, entity, job, client, analysis) is not None:
                    written += 1
        except Exception as exc:  # noqa: BLE001 -- one bad bill shouldn't kill the batch
            db.rollback()
            failed += 1
            logger.warning("FAIL %s: %s", entity.bill.bill_number, exc)
    return written, failed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Max bills with work to process this run.")
    parser.add_argument("--dry-run", action="store_true", help="List planned jobs; no model calls, no writes.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.dry_run:
            n = 0
            for entity in _bills(db):
                jobs = plan_jobs(db, entity, settings.ollama_model) if entity.bill else []
                if jobs:
                    n += 1
                    print(f"{entity.bill.bill_number}: " + ", ".join(f"{j.layer}/{j.origin}" for j in jobs))
                    if args.limit and n >= args.limit:
                        break
            print(f"\n{n} bill(s) with work.")
        else:
            ok, bad = process_bills(db, OllamaClient(), limit=args.limit)
            print(f"\nDone: {ok} block version(s) written, {bad} bill(s) failed.")
    finally:
        db.close()
```

Note on the test expectation `written == 2` in `test_new_staff_analysis_versions_only_staff_blocks`: both staff inputs include the new label, so both staff blocks re-version, and the three bill-text blocks don't. The `RoutingClient` returns the same payload, but the hash differs, so the rows are written.

- [ ] **Step 4: Run and confirm pass**

Same command. Expected: 5 passed.

- [ ] **Step 5: Add the nightly step (not enabled on the host yet)**

In `scripts/run-ingestion.sh`, after the `step "Summarize new/changed bills" ...` line, add:
```bash
# Bill page layers (Bill Says / Interpretation / Expected Effect). Only
# re-generates blocks whose inputs changed. Capped per night so a large
# backlog (e.g. after a prompt change) can't run into the morning.
step "Bill layers" docker exec "$CONTAINER" python -m app.pipeline.bill_layers_batch --limit 150
```
Also update the header comment's step list: after "summarize anything new," add "update bill page layers,". The host copy is updated only at rollout (Task 11).

- [ ] **Step 6: Commit**

```bash
git add backend/app/pipeline/bill_layers_batch.py backend/tests/test_bill_layers_batch.py scripts/run-ingestion.sh
git commit -m "Add bill layers batch job and nightly step"
```

---

### Task 6: Review endpoints

**Files:**
- Create: `backend/app/api/bill_layers_admin.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_bill_layers_admin.py`

**Interfaces:**
- Consumes: `BillLayer`, `BillLayerReview` (Task 1); `require_admin` from `app.auth`.
- Produces:
  - `GET /bill-layers/admin/unreviewed?limit=N` (1–200, default 50): current versions with no approval, oldest first. Each is `{id, bill_entity_id, bill_number, layer, origin, version, evidence_state, scope_note, items, created_at, sources: [{url, source_type}]}`.
  - `POST /bill-layers/admin/{layer_id}/review` with body `{"decision": "approved", "note": str | null}` returns `{"id", "bill_layer_id", "decision", "created_at"}`, status 201. Returns 404 if the id is unknown, 409 if the version is superseded, and 409 if it's already approved.
  - `review_state(layer: BillLayer) -> tuple[str, datetime | None]`: `("reviewed", first approval time)` or `("not_reviewed", None)`. Used by Task 7.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_bill_layers_admin.py`:
```python
from datetime import datetime, timezone

from app.models import BillLayer

AUTH = ("testadmin", "testpass")


def _layer(db, entity, version=1, superseded=False):
    row = BillLayer(
        bill_entity_id=entity.id, layer="interpretation", origin="sunshine_ledger_ai", version=version,
        superseded_at=datetime.now(timezone.utc) if superseded else None, evidence_state="supported",
        scope_note="Bill text", items=[{"text": "t", "section_ref": "Section 1", "quote": None, "assumptions": [], "affected_groups": []}],
        generated_by="llm:test", method_version="interpretation/sunshine_ledger_ai/1", input_hash=f"h{version}",
    )
    db.add(row)
    db.commit()
    return row


def test_review_endpoints_require_auth(client):
    assert client.get("/bill-layers/admin/unreviewed").status_code == 401


def test_unreviewed_lists_current_unapproved_only(client, db_session, bill_factory):
    entity = bill_factory()
    _layer(db_session, entity, version=1, superseded=True)
    current = _layer(db_session, entity, version=2)
    body = client.get("/bill-layers/admin/unreviewed", auth=AUTH).json()
    assert [b["id"] for b in body] == [str(current.id)]
    assert body[0]["bill_number"] == "HB 123"


def test_approve_current_version(client, db_session, bill_factory):
    entity = bill_factory()
    row = _layer(db_session, entity)
    resp = client.post(f"/bill-layers/admin/{row.id}/review", json={"decision": "approved", "note": "checked"}, auth=AUTH)
    assert resp.status_code == 201
    assert "reviewer" not in resp.json() and "note" not in resp.json()
    assert client.get("/bill-layers/admin/unreviewed", auth=AUTH).json() == []


def test_approving_superseded_version_is_409(client, db_session, bill_factory):
    entity = bill_factory()
    old = _layer(db_session, entity, version=1, superseded=True)
    resp = client.post(f"/bill-layers/admin/{old.id}/review", json={"decision": "approved"}, auth=AUTH)
    assert resp.status_code == 409


def test_double_approval_is_409(client, db_session, bill_factory):
    entity = bill_factory()
    row = _layer(db_session, entity)
    client.post(f"/bill-layers/admin/{row.id}/review", json={"decision": "approved"}, auth=AUTH)
    assert client.post(f"/bill-layers/admin/{row.id}/review", json={"decision": "approved"}, auth=AUTH).status_code == 409


def test_only_approved_decision_accepted(client, db_session, bill_factory):
    entity = bill_factory()
    row = _layer(db_session, entity)
    assert client.post(f"/bill-layers/admin/{row.id}/review", json={"decision": "rejected"}, auth=AUTH).status_code == 422
```

- [ ] **Step 2: Run and confirm failure**

One-file command with `tests/test_bill_layers_admin.py`. Expected: 404s or assertion failures, because the route doesn't exist.

- [ ] **Step 3: Implement**

`backend/app/api/bill_layers_admin.py`:
```python
"""Admin-only human review of bill layer versions.

Review is recorded as an append-only BillLayerReview row -- never an edit
to the reviewed BillLayer. Only the current version can be reviewed: a
superseded one is history. No rejection path in this version; problems go
through a flag and the corrections process.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_admin
from app.db import get_db
from app.models import BillLayer, BillLayerReview, BillLayerSource, Entity

router = APIRouter(prefix="/bill-layers/admin", tags=["bill-layers-admin"])


def review_state(layer: BillLayer) -> tuple[str, datetime | None]:
    approvals = [r for r in layer.reviews if r.decision == "approved"]
    if not approvals:
        return "not_reviewed", None
    return "reviewed", min(r.created_at for r in approvals)


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^approved$")
    note: str | None = Field(default=None, max_length=2000)


class ReviewOut(BaseModel):
    id: uuid.UUID
    bill_layer_id: uuid.UUID
    decision: str
    created_at: datetime


class UnreviewedSourceOut(BaseModel):
    url: str
    source_type: str


class UnreviewedOut(BaseModel):
    id: uuid.UUID
    bill_entity_id: uuid.UUID
    bill_number: str
    layer: str
    origin: str
    version: int
    evidence_state: str
    scope_note: str
    items: list[dict]
    created_at: datetime
    sources: list[UnreviewedSourceOut]


@router.get("/unreviewed", response_model=list[UnreviewedOut])
def list_unreviewed(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
) -> list[UnreviewedOut]:
    approved = select(BillLayerReview.bill_layer_id).where(BillLayerReview.decision == "approved")
    rows = db.execute(
        select(BillLayer, Entity)
        .join(Entity, Entity.id == BillLayer.bill_entity_id)
        .where(BillLayer.superseded_at.is_(None), BillLayer.id.not_in(approved))
        .options(selectinload(BillLayer.source_links).selectinload(BillLayerSource.source), selectinload(Entity.bill))
        .order_by(BillLayer.created_at)
        .limit(limit)
    ).all()
    return [
        UnreviewedOut(
            id=layer.id, bill_entity_id=layer.bill_entity_id,
            bill_number=entity.bill.bill_number if entity.bill else "?",
            layer=layer.layer, origin=layer.origin, version=layer.version,
            evidence_state=layer.evidence_state, scope_note=layer.scope_note, items=layer.items,
            created_at=layer.created_at,
            sources=[UnreviewedSourceOut(url=l.source.url, source_type=l.source.source_type) for l in layer.source_links],
        )
        for layer, entity in rows
    ]


@router.post("/{layer_id}/review", response_model=ReviewOut, status_code=201)
def review_layer(
    layer_id: uuid.UUID,
    payload: ReviewIn,
    db: Session = Depends(get_db),
    admin: str = Depends(require_admin),
) -> ReviewOut:
    layer = db.execute(
        select(BillLayer).where(BillLayer.id == layer_id).options(selectinload(BillLayer.reviews))
    ).scalar_one_or_none()
    if layer is None:
        raise HTTPException(status_code=404, detail="Bill layer not found")
    if layer.superseded_at is not None:
        raise HTTPException(status_code=409, detail="This version is superseded; review the current version")
    if review_state(layer)[0] == "reviewed":
        raise HTTPException(status_code=409, detail="Already approved")
    review = BillLayerReview(bill_layer_id=layer.id, decision=payload.decision, reviewer=admin, note=payload.note)
    db.add(review)
    db.commit()
    db.refresh(review)
    return ReviewOut(id=review.id, bill_layer_id=review.bill_layer_id, decision=review.decision, created_at=review.created_at)
```

In `backend/app/main.py`, add `bill_layers_admin` to the `from app.api import ...` line and add `app.include_router(bill_layers_admin.router)` after `app.include_router(flags.router)`.

- [ ] **Step 4: Run and confirm pass**

Same command. Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/bill_layers_admin.py backend/app/main.py backend/tests/test_bill_layers_admin.py
git commit -m "Add admin review endpoints for bill layer versions"
```

---

### Task 7: Layers in the bill detail API

**Files:**
- Modify: `backend/app/schemas/bill.py`
- Modify: `backend/app/api/bills.py`
- Test: `backend/tests/test_bill_layers_api.py`

**Interfaces:**
- Consumes: `BillLayer`, `BillLayerSource`, `StaffAnalysis`; `review_state` (Task 6).
- Produces, in `app.schemas.bill`:
  - `LayerItemOut {text: str, section_ref: str | None, quote: str | None, assumptions: list[str], affected_groups: list[str]}`
  - `LayerVersionOut {id, version, evidence_state, review_status, reviewed_at: datetime | None, scope_note, items: list[LayerItemOut], generated_by, method_version, created_at, superseded_at: datetime | None, sources: list[SourceOut]}`
  - `LayerBlockOut {origin: str, current: LayerVersionOut, earlier_versions: list[LayerVersionOut]}`: earlier versions newest first.
  - `BillLayersOut {bill_says: list[LayerBlockOut], interpretation: list[LayerBlockOut], expected_effect: list[LayerBlockOut]}`
  - `BillDetail.layers: BillLayersOut`, `BillDetail.has_staff_analysis: bool`
- Produces, in `app.api.bills`: `_layers_for_bill(db, entity_id) -> BillLayersOut`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_bill_layers_api.py`:
```python
from datetime import date, datetime, timedelta, timezone

from app.models import BillLayer, BillLayerReview, StaffAnalysis


def _row(db, entity, layer, origin, version=1, superseded=False, text="t"):
    row = BillLayer(
        bill_entity_id=entity.id, layer=layer, origin=origin, version=version,
        superseded_at=datetime.now(timezone.utc) if superseded else None, evidence_state="supported",
        scope_note="Bill text", items=[{"text": text, "section_ref": "Section 1", "quote": None, "assumptions": [], "affected_groups": []}],
        generated_by="llm:test", method_version=f"{layer}/{origin}/1", input_hash=f"{layer}{origin}{version}",
    )
    db.add(row)
    db.commit()
    return row


def test_bill_without_layers_has_empty_layers(client, bill_factory):
    entity = bill_factory()
    body = client.get(f"/bills/{entity.id}").json()
    assert body["layers"] == {"bill_says": [], "interpretation": [], "expected_effect": []}
    assert body["has_staff_analysis"] is False


def test_blocks_are_grouped_by_layer_with_earlier_versions(client, db_session, bill_factory):
    entity = bill_factory()
    _row(db_session, entity, "interpretation", "sunshine_ledger_ai", version=1, superseded=True, text="old")
    _row(db_session, entity, "interpretation", "sunshine_ledger_ai", version=2, text="new")
    _row(db_session, entity, "bill_says", "bill_text")
    layers = client.get(f"/bills/{entity.id}").json()["layers"]
    assert [b["origin"] for b in layers["bill_says"]] == ["bill_text"]
    block = layers["interpretation"][0]
    assert block["origin"] == "sunshine_ledger_ai"
    assert block["current"]["items"][0]["text"] == "new"
    assert [v["items"][0]["text"] for v in block["earlier_versions"]] == ["old"]
    assert layers["expected_effect"] == []


def test_review_status_is_derived_and_private_fields_hidden(client, db_session, bill_factory):
    entity = bill_factory()
    row = _row(db_session, entity, "interpretation", "sunshine_ledger_ai")
    db_session.add(BillLayerReview(bill_layer_id=row.id, decision="approved", reviewer="joe", note="secret"))
    db_session.commit()
    resp = client.get(f"/bills/{entity.id}")
    current = resp.json()["layers"]["interpretation"][0]["current"]
    assert current["review_status"] == "reviewed" and current["reviewed_at"] is not None
    assert "joe" not in resp.text and "secret" not in resp.text


def test_new_version_after_review_starts_unreviewed(client, db_session, bill_factory):
    entity = bill_factory()
    old = _row(db_session, entity, "interpretation", "sunshine_ledger_ai", version=1)
    db_session.add(BillLayerReview(bill_layer_id=old.id, decision="approved", reviewer="joe"))
    old.superseded_at = datetime.now(timezone.utc)
    db_session.commit()
    _row(db_session, entity, "interpretation", "sunshine_ledger_ai", version=2)
    block = client.get(f"/bills/{entity.id}").json()["layers"]["interpretation"][0]
    assert block["current"]["review_status"] == "not_reviewed"
    assert block["earlier_versions"][0]["review_status"] == "reviewed"


def test_has_staff_analysis(client, db_session, bill_factory):
    entity = bill_factory()
    db_session.add(StaffAnalysis(entity_id=entity.id, legiscan_supplement_id=77, committee="Rules",
                                 analysis_date=date(2026, 3, 1), source_url="https://x/a.pdf", text="III. Effect"))
    db_session.commit()
    assert client.get(f"/bills/{entity.id}").json()["has_staff_analysis"] is True
```

- [ ] **Step 2: Run and confirm failure**

One-file command with `tests/test_bill_layers_api.py`. Expected: `KeyError: 'layers'`.

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas/bill.py`, before `class BillDetail`, add:
```python
class LayerItemOut(BaseModel):
    text: str
    section_ref: str | None = None
    quote: str | None = None
    assumptions: list[str] = []
    affected_groups: list[str] = []


class LayerVersionOut(BaseModel):
    id: uuid.UUID
    version: int
    evidence_state: str
    review_status: str
    reviewed_at: datetime | None
    scope_note: str
    items: list[LayerItemOut]
    generated_by: str
    method_version: str
    created_at: datetime
    superseded_at: datetime | None
    sources: list[SourceOut]


class LayerBlockOut(BaseModel):
    """One (layer, origin) block: its current version plus history, newest
    first. `origin` is a fixed backend value; the frontend maps it to
    display text through one lookup, never by position or content."""

    origin: str
    current: LayerVersionOut
    earlier_versions: list[LayerVersionOut]


class BillLayersOut(BaseModel):
    bill_says: list[LayerBlockOut] = []
    interpretation: list[LayerBlockOut] = []
    expected_effect: list[LayerBlockOut] = []
```
Add to `BillDetail`:
```python
    layers: BillLayersOut
    has_staff_analysis: bool
```

- [ ] **Step 4: Build `layers` in the API**

In `backend/app/api/bills.py`:
- Add `BillLayer, BillLayerSource, StaffAnalysis` to the `from app.models import ...` line.
- Add `BillLayersOut, LayerBlockOut, LayerItemOut, LayerVersionOut` to the schema import.
- Add `from app.api.bill_layers_admin import review_state`.
- Add the helper:
```python
_ORIGIN_ORDER = {"bill_text": 0, "legislative_staff": 1, "sunshine_ledger_ai": 2}


def _layer_version_out(row: BillLayer) -> LayerVersionOut:
    status, reviewed_at = review_state(row)
    return LayerVersionOut(
        id=row.id, version=row.version, evidence_state=row.evidence_state,
        review_status=status, reviewed_at=reviewed_at, scope_note=row.scope_note,
        items=[LayerItemOut(**i) for i in row.items], generated_by=row.generated_by,
        method_version=row.method_version, created_at=row.created_at, superseded_at=row.superseded_at,
        sources=[SourceOut.model_validate(link.source) for link in row.source_links],
    )


def _layers_for_bill(db: Session, entity_id: uuid.UUID) -> BillLayersOut:
    rows = db.execute(
        select(BillLayer)
        .where(BillLayer.bill_entity_id == entity_id)
        .options(selectinload(BillLayer.source_links).selectinload(BillLayerSource.source), selectinload(BillLayer.reviews))
        .order_by(BillLayer.version.desc())
    ).scalars().all()
    grouped: dict[tuple[str, str], list[BillLayer]] = {}
    for row in rows:
        grouped.setdefault((row.layer, row.origin), []).append(row)

    out = BillLayersOut()
    for (layer, origin), versions in sorted(grouped.items(), key=lambda kv: _ORIGIN_ORDER[kv[0][1]]):
        current = next((v for v in versions if v.superseded_at is None), None)
        if current is None:
            continue
        getattr(out, layer).append(LayerBlockOut(
            origin=origin,
            current=_layer_version_out(current),
            earlier_versions=[_layer_version_out(v) for v in versions if v.id != current.id],
        ))
    return out
```
- In `get_bill`, add to the `BillDetail(...)` call:
```python
        layers=_layers_for_bill(db, entity_id),
        has_staff_analysis=db.execute(
            select(StaffAnalysis.id).where(StaffAnalysis.entity_id == entity_id).limit(1)
        ).first() is not None,
```

- [ ] **Step 5: Run and confirm pass, then the full backend suite**

Same command, then `./scripts/run-tests.sh`. Expected: new tests pass; existing `tests/test_bills_api.py` still passes (new fields are additive).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/bill.py backend/app/api/bills.py backend/tests/test_bill_layers_api.py
git commit -m "Expose bill layers and staff-analysis presence on bill detail API"
```

---

### Task 8: Quality-gate report

**Files:**
- Create: `backend/app/pipeline/review_bill_layers.py`

**Interfaces:**
- Consumes: `plan_jobs` inputs, `gen.build_*`, `latest_staff_analysis`, `staff_label`, `extract_*` (Tasks 2, 3, 5).
- Produces: CLI `python -m app.pipeline.review_bill_layers --sample N [--bill "HB 123" ...]` that prints a markdown report to stdout. **No DB writes**: it never calls `store_layer_version`, and it rolls back the session at the end.

This task is a manual-verification tool with no unit test. Its correctness check is that it runs end-to-end in Task 11 and writes nothing (verified by counting `bill_layers` rows before and after).

- [ ] **Step 1: Implement**

`backend/app/pipeline/review_bill_layers.py`:
```python
"""Quality gate for bill layers: generate every block for a sample of real
bills and print a markdown report. Writes NOTHING to the database -- the
person reading the report decides whether the backfill goes ahead.

Sample: half bills with a staff analysis, half without (state and local),
so both origins and both staff formats are exercised.

Usage:
    python -m app.pipeline.review_bill_layers --sample 20 > layers-review.md
    python -m app.pipeline.review_bill_layers --bill "HB 123" --bill "SB 7"
"""

from __future__ import annotations

import argparse

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import Bill, Entity, StaffAnalysis
from app.pipeline import bill_layers as gen
from app.pipeline.bill_layers_batch import latest_staff_analysis, staff_label
from app.pipeline.bill_layers_text import extract_effect_section, extract_fiscal_section
from app.pipeline.summarize import OllamaClient


def _sample(db, n: int, bill_numbers: list[str]) -> list[Entity]:
    base = select(Entity).join(Bill, Bill.entity_id == Entity.id).options(selectinload(Entity.bill))
    if bill_numbers:
        return list(db.execute(base.where(Bill.bill_number.in_(bill_numbers))).scalars().all())
    has_staff = select(StaffAnalysis.entity_id)
    with_staff = db.execute(
        base.where(Bill.full_text.isnot(None), Entity.id.in_(has_staff)).order_by(func.random()).limit(n // 2)
    ).scalars().all()
    without = db.execute(
        base.where(Bill.full_text.isnot(None), Entity.id.not_in(has_staff)).order_by(func.random()).limit(n - n // 2)
    ).scalars().all()
    return list(with_staff) + list(without)


def _render(title: str, result: gen.LayerResult) -> list[str]:
    lines = [f"#### {title}", f"- state: `{result.evidence_state}` · scope: {result.scope_note}"]
    for i in result.items:
        ref = f" ({i['section_ref']})" if i.get("section_ref") else ""
        lines.append(f"- {i['text']}{ref}")
        for a in i.get("assumptions") or []:
            lines.append(f"  - assumption: {a}")
    for d in result.dropped:
        lines.append(f"- ~~dropped~~: `{d}`")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--bill", action="append", default=[])
    args = parser.parse_args()

    client = OllamaClient()
    db = SessionLocal()
    kept_quotes = dropped_quotes = kept_effects = dropped_effects = 0
    out: list[str] = [f"# Bill layers quality review ({client.model})", ""]
    try:
        for entity in _sample(db, args.sample, args.bill):
            bill = entity.bill
            out += [f"## {bill.bill_number} — {entity.name}", ""]
            try:
                says = gen.build_bill_says(bill.bill_number, entity.name, bill.full_text or "", client)
                kept_quotes += len(says.items)
                dropped_quotes += len(says.dropped)
                out += _render("Bill Says · bill text", says)
                out += _render("Interpretation · Sunshine Ledger",
                               gen.build_ai_interpretation(bill.bill_number, entity.name, bill.full_text or "", client))
                ai_eff = gen.build_ai_expected_effect(bill.bill_number, entity.name, bill.full_text or "", client)
                kept_effects += len(ai_eff.items)
                dropped_effects += len(ai_eff.dropped)
                out += _render("Expected Effect · Sunshine Ledger", ai_eff)
                analysis = latest_staff_analysis(db, entity.id)
                if analysis is None:
                    out.append("_No staff analysis published._")
                else:
                    label = staff_label(analysis)
                    out += _render("Interpretation · staff",
                                   gen.build_staff_interpretation(extract_effect_section(analysis.text), label, client))
                    out += _render("Expected Effect · staff",
                                   gen.build_staff_expected_effect(extract_fiscal_section(analysis.text), label, client))
            except gen.LayerGenerationError as exc:
                out.append(f"**Generation error:** {exc}")
            out.append("")
        total_q = kept_quotes + dropped_quotes
        total_e = kept_effects + dropped_effects
        out[1:1] = [
            f"- Bill Says quotes verified: {kept_quotes}/{total_q}" if total_q else "- Bill Says quotes: none returned",
            f"- Sunshine Ledger effects kept after guards: {kept_effects}/{total_e}" if total_e else "- Sunshine Ledger effects: none returned",
            "",
        ]
        print("\n".join(out))
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Check it imports cleanly in the test stack**

```bash
docker --context desktop-linux compose -f docker-compose.test.yml run --rm backend-test \
  sh -c "pip install -q -r requirements-dev.txt && python -c 'import app.pipeline.review_bill_layers'"; \
docker --context desktop-linux compose -f docker-compose.test.yml down -v
```
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add backend/app/pipeline/review_bill_layers.py
git commit -m "Add bill layers quality-gate report (read-only)"
```

---

### Task 9: Frontend types, label lookup and BillLayers component

**Files:**
- Modify: `frontend/lib/types.ts`
- Create: `frontend/lib/layers.ts`
- Create: `frontend/components/BillLayers.tsx`
- Test: `frontend/components/BillLayers.test.tsx`

**Interfaces:**
- Consumes: the API shape from Task 7.
- Produces:
  - Types `LayerItem`, `LayerVersion`, `LayerBlock`, `BillLayers`; `BillDetail.layers: BillLayers`; `BillDetail.has_staff_analysis: boolean`.
  - `lib/layers.ts`: `LAYER_ORDER`, `LAYER_META: Record<LayerKey, {title, definition}>`, `ORIGINS_FOR_LAYER: Record<LayerKey, Origin[]>`, `originBadge(origin, version) -> string`, `reviewLabel(version) -> string | null`, `hasAnyLayer(layers) -> boolean`.
  - `<BillLayers layers hasStaffAnalysis fallbackSummary />` (default export).

- [ ] **Step 1: Repair frontend dependencies**

```bash
cd frontend && rm -rf node_modules && npm ci && npx vitest run && cd ..
```
Expected: existing suites pass (97 tests as of 2026-09-23).

- [ ] **Step 2: Add the types**

Append to `frontend/lib/types.ts`:
```ts
export type LayerKey = "bill_says" | "interpretation" | "expected_effect";
export type Origin = "bill_text" | "legislative_staff" | "sunshine_ledger_ai";

export interface LayerItem {
  text: string;
  section_ref: string | null;
  quote: string | null;
  assumptions: string[];
  affected_groups: string[];
}

export interface LayerVersion {
  id: string;
  version: number;
  evidence_state: "supported" | "insufficient_evidence";
  review_status: "not_reviewed" | "reviewed";
  reviewed_at: string | null;
  scope_note: string;
  items: LayerItem[];
  generated_by: string;
  method_version: string;
  created_at: string;
  superseded_at: string | null;
  sources: SourceOut[];
}

export interface LayerBlock {
  origin: Origin;
  current: LayerVersion;
  earlier_versions: LayerVersion[];
}

export type BillLayers = Record<LayerKey, LayerBlock[]>;
```
In `interface BillDetail`, add:
```ts
  layers: BillLayers;
  has_staff_analysis: boolean;
```
(`SourceOut` already exists in this file. If its name differs, use the type `ClaimOut.sources` uses.)

- [ ] **Step 3: Write the failing component tests**

`frontend/components/BillLayers.test.tsx`:
```tsx
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import BillLayers from "./BillLayers";
import type { BillLayers as Layers, LayerVersion } from "@/lib/types";

function version(overrides: Partial<LayerVersion> = {}): LayerVersion {
  return {
    id: "v1", version: 1, evidence_state: "supported", review_status: "not_reviewed", reviewed_at: null,
    scope_note: "Bill text", generated_by: "llm:llama3.1:8b", method_version: "x/1",
    created_at: "2026-09-23T00:00:00Z", superseded_at: null, sources: [],
    items: [{ text: "Item text", section_ref: "Section 1", quote: null, assumptions: [], affected_groups: [] }],
    ...overrides,
  };
}

const empty: Layers = { bill_says: [], interpretation: [], expected_effect: [] };

function section(name: RegExp) {
  return screen.getByRole("region", { name });
}

describe("BillLayers", () => {
  it("renders each block only under its own layer heading", () => {
    const layers: Layers = {
      ...empty,
      interpretation: [{ origin: "sunshine_ledger_ai", current: version({ items: [{ text: "Interp only", section_ref: "Section 1", quote: null, assumptions: [], affected_groups: [] }] }), earlier_versions: [] }],
    };
    render(<BillLayers layers={layers} hasStaffAnalysis={false} fallbackSummary={null} />);
    expect(within(section(/Interpretation/)).getByText("Interp only")).toBeInTheDocument();
    expect(within(section(/Expected Effect/)).queryByText("Interp only")).toBeNull();
    expect(within(section(/Bill Says/)).queryByText("Interp only")).toBeNull();
  });

  it("shows the exact empty states", () => {
    render(<BillLayers layers={empty} hasStaffAnalysis={false} fallbackSummary={null} />);
    const interp = section(/Interpretation/);
    expect(within(interp).getByText("No staff analysis published.")).toBeInTheDocument();
    expect(within(interp).getByText("Not yet evaluated.")).toBeInTheDocument();
  });

  it("says not yet evaluated for a staff block when an analysis exists", () => {
    render(<BillLayers layers={empty} hasStaffAnalysis={true} fallbackSummary={null} />);
    expect(within(section(/Interpretation/)).getAllByText("Not yet evaluated.")).toHaveLength(2);
  });

  it("labels AI blocks by review status and Bill Says by quote checking", () => {
    const layers: Layers = {
      bill_says: [{ origin: "bill_text", current: version({ items: [{ text: "Quoted", section_ref: "Section 2", quote: "Quoted", assumptions: [], affected_groups: [] }] }), earlier_versions: [] }],
      interpretation: [
        { origin: "legislative_staff", current: version({ scope_note: "Staff analysis, Rules, 2026-03-01", review_status: "reviewed", reviewed_at: "2026-09-30T00:00:00Z" }), earlier_versions: [] },
        { origin: "sunshine_ledger_ai", current: version(), earlier_versions: [] },
      ],
      expected_effect: [],
    };
    render(<BillLayers layers={layers} hasStaffAnalysis={true} fallbackSummary={null} />);
    expect(within(section(/Bill Says/)).getByText("Quotes checked word for word against the bill text")).toBeInTheDocument();
    const interp = section(/Interpretation/);
    expect(within(interp).getByText(/Legislative staff analysis · Rules, 2026-03-01 · condensed by AI/)).toBeInTheDocument();
    expect(within(interp).getByText(/reviewed by a person on Sep 30, 2026/)).toBeInTheDocument();
    expect(within(interp).getByText(/Sunshine Ledger analysis · AI-generated/)).toBeInTheDocument();
    expect(within(interp).getByText(/not reviewed by a person/)).toBeInTheDocument();
  });

  it("shows insufficient evidence with its scope note", () => {
    const layers: Layers = {
      ...empty,
      expected_effect: [{ origin: "sunshine_ledger_ai", current: version({ evidence_state: "insufficient_evidence", items: [], scope_note: "No effects traceable to a specific bill section" }), earlier_versions: [] }],
    };
    render(<BillLayers layers={layers} hasStaffAnalysis={false} fallbackSummary={null} />);
    expect(within(section(/Expected Effect/)).getByText(/Insufficient evidence/)).toBeInTheDocument();
    expect(within(section(/Expected Effect/)).getByText(/No effects traceable to a specific bill section/)).toBeInTheDocument();
  });

  it("includes the Expected Effect disclaimer", () => {
    render(<BillLayers layers={empty} hasStaffAnalysis={false} fallbackSummary={null} />);
    expect(screen.getByText("What may happen. Forecasts, not established facts, and not legal or financial advice.")).toBeInTheDocument();
  });

  it("lists earlier versions", () => {
    const layers: Layers = {
      ...empty,
      interpretation: [{
        origin: "sunshine_ledger_ai",
        current: version({ version: 2 }),
        earlier_versions: [version({ id: "v0", version: 1, superseded_at: "2026-09-20T00:00:00Z", items: [{ text: "Older reading", section_ref: null, quote: null, assumptions: [], affected_groups: [] }] })],
      }],
    };
    render(<BillLayers layers={layers} hasStaffAnalysis={false} fallbackSummary={null} />);
    expect(screen.getByText("1 earlier version")).toBeInTheDocument();
    expect(screen.getByText("Older reading")).toBeInTheDocument();
  });

  it("links a staff block to the analysis PDF with its retrieval date", () => {
    const layers: Layers = {
      ...empty,
      interpretation: [{
        origin: "legislative_staff",
        current: version({
          scope_note: "Staff analysis, Rules, 2026-03-01",
          sources: [{ id: "s1", url: "https://flsenate.gov/a.pdf", publisher: "Florida Legislature staff", source_type: "fl_staff_analysis", retrieved_at: "2026-09-23T00:00:00Z" }],
        }),
        earlier_versions: [],
      }],
    };
    render(<BillLayers layers={layers} hasStaffAnalysis={true} fallbackSummary={null} />);
    expect(screen.getByRole("link", { name: "staff analysis (PDF)" })).toHaveAttribute("href", "https://flsenate.gov/a.pdf");
    expect(screen.getByText(/retrieved Sep 23, 2026/)).toBeInTheDocument();
  });

  it("falls back to the labeled summary when there is no Bill Says", () => {
    render(<BillLayers layers={empty} hasStaffAnalysis={false} fallbackSummary="Plain summary." />);
    const says = section(/Bill Says/);
    expect(within(says).getByText("AI summary of the official description")).toBeInTheDocument();
    expect(within(says).getByText("Plain summary.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Run and confirm failure**

`cd frontend && npx vitest run components/BillLayers.test.tsx`. Expected: cannot resolve `./BillLayers`.

- [ ] **Step 5: Implement the label lookup**

`frontend/lib/layers.ts`:
```ts
// The one place layer and origin keys become display text. Components never
// derive a heading or badge from block position or content -- only from
// these keys -- so a block can't be rendered under the wrong label.
import type { BillLayers, LayerKey, LayerVersion, Origin } from "@/lib/types";

export const LAYER_ORDER: LayerKey[] = ["bill_says", "interpretation", "expected_effect"];

export const LAYER_META: Record<LayerKey, { title: string; definition: string }> = {
  bill_says: { title: "Bill Says", definition: "The bill's own words." },
  interpretation: { title: "Interpretation", definition: "What the change means." },
  expected_effect: {
    title: "Expected Effect",
    definition: "What may happen. Forecasts, not established facts, and not legal or financial advice.",
  },
};

export const ORIGINS_FOR_LAYER: Record<LayerKey, Origin[]> = {
  bill_says: ["bill_text"],
  interpretation: ["legislative_staff", "sunshine_ledger_ai"],
  expected_effect: ["legislative_staff", "sunshine_ledger_ai"],
};

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

export function originBadge(origin: Origin, version: LayerVersion | null): string {
  if (origin === "bill_text") return "Bill text";
  if (origin === "legislative_staff") {
    // scope_note is "Staff analysis, <committee>, <date>" for staff blocks.
    const detail = version?.scope_note.replace(/^Staff analysis, /, "").replace(/ has no .*$/, "").replace(/:.*$/, "");
    return detail ? `Legislative staff analysis · ${detail} · condensed by AI` : "Legislative staff analysis";
  }
  return "Sunshine Ledger analysis · AI-generated";
}

export function reviewLabel(origin: Origin, version: LayerVersion): string | null {
  if (origin === "bill_text") return null;
  if (version.review_status === "reviewed" && version.reviewed_at) {
    return `reviewed by a person on ${formatDate(version.reviewed_at)}`;
  }
  return "not reviewed by a person";
}

export function hasAnyLayer(layers: BillLayers | undefined): boolean {
  return !!layers && LAYER_ORDER.some((k) => layers[k].length > 0);
}
```

- [ ] **Step 6: Implement the component**

`frontend/components/BillLayers.tsx`:
```tsx
import type { BillLayers as Layers, LayerBlock, LayerKey, LayerVersion, Origin } from "@/lib/types";
import { LAYER_META, LAYER_ORDER, ORIGINS_FOR_LAYER, formatDate, originBadge, reviewLabel } from "@/lib/layers";

/** The three separately labeled layers on a bill page. Pure display --
 *  server-rendered, no interactivity beyond native <details>. */

type Props = {
  layers: Layers;
  hasStaffAnalysis: boolean;
  /** Existing "what it does" summary, shown under Bill Says only as a
   *  labeled fallback -- never presented as the bill's own words. */
  fallbackSummary: string | null;
};

const BADGE_STYLE: Record<Origin, string> = {
  bill_text: "bg-slate-100 text-slate-700",
  legislative_staff: "bg-slate-100 text-slate-700",
  sunshine_ledger_ai: "bg-sunshine-100 text-sunshine-600",
};

function VersionBody({ layer, version }: { layer: LayerKey; version: LayerVersion }) {
  if (version.evidence_state === "insufficient_evidence") {
    return (
      <p className="mt-1 text-sm text-slate-600">
        <span className="font-medium">Insufficient evidence</span> — {version.scope_note}
      </p>
    );
  }
  return (
    <ul className="mt-1 space-y-2 text-sm leading-relaxed text-slate-700">
      {version.items.map((item, i) => (
        <li key={i}>
          {layer === "bill_says" && item.quote ? (
            <blockquote className="border-l-2 border-slate-300 pl-2 italic">&ldquo;{item.quote}&rdquo;</blockquote>
          ) : (
            <span>{item.text}</span>
          )}
          {item.section_ref && <span className="ml-1 text-xs text-slate-500">({item.section_ref})</span>}
          {item.assumptions.length > 0 && (
            <div className="mt-0.5 text-xs text-slate-500">
              Assumptions: {item.assumptions.join("; ")}
            </div>
          )}
          {item.affected_groups.length > 0 && (
            <div className="mt-0.5 text-xs text-slate-500">Affected groups: {item.affected_groups.join(", ")}</div>
          )}
        </li>
      ))}
    </ul>
  );
}

function Block({ layer, origin, block, hasStaffAnalysis }: {
  layer: LayerKey; origin: Origin; block: LayerBlock | undefined; hasStaffAnalysis: boolean;
}) {
  const version = block?.current ?? null;
  const review = version ? reviewLabel(origin, version) : null;
  return (
    <div className="mt-3 rounded border border-slate-200 p-3">
      <h3 className="text-xs font-medium">
        <span className={`rounded px-1.5 py-0.5 ${BADGE_STYLE[origin]}`}>{originBadge(origin, version)}</span>
        {review && (
          <span className={`ml-1.5 ${version?.review_status === "reviewed" ? "text-ledger-900" : "text-slate-500"}`}>
            · {review}
          </span>
        )}
      </h3>
      {!version ? (
        <p className="mt-1 text-sm text-slate-600">
          {origin === "legislative_staff" && !hasStaffAnalysis ? "No staff analysis published." : "Not yet evaluated."}
        </p>
      ) : (
        <>
          <VersionBody layer={layer} version={version} />
          {origin === "bill_text" && version.evidence_state === "supported" && (
            <p className="mt-1 text-[11px] text-slate-500">Quotes checked word for word against the bill text</p>
          )}
          {version.scope_note === "Drawn from the first part of a long bill" && (
            <p className="mt-1 text-[11px] text-slate-500">Drawn from the first part of a long bill</p>
          )}
          {version.sources.length > 0 && (
            <p className="mt-2 text-[11px] text-slate-500">
              Source:{" "}
              {version.sources.map((s, i) => (
                <span key={s.id}>
                  {i > 0 && "; "}
                  {s.url ? (
                    <a href={s.url} className="underline hover:text-slate-700">
                      {origin === "legislative_staff" ? "staff analysis (PDF)" : "bill text"}
                    </a>
                  ) : (
                    origin === "legislative_staff" ? "staff analysis" : "bill text"
                  )}{" "}
                  (retrieved {formatDate(s.retrieved_at)})
                </span>
              ))}
            </p>
          )}
          <p className="mt-1 text-[11px] text-slate-400">
            {version.generated_by.replace(/^llm:/, "Model: ")} · method {version.method_version} · updated{" "}
            {formatDate(version.created_at)}
          </p>
          {block && block.earlier_versions.length > 0 && (
            <details className="mt-1 text-xs text-slate-500">
              <summary className="cursor-pointer underline">
                {block.earlier_versions.length} earlier version{block.earlier_versions.length === 1 ? "" : "s"}
              </summary>
              {block.earlier_versions.map((v) => (
                <div key={v.id} className="mt-2 border-t border-slate-100 pt-1">
                  <div>
                    Version {v.version} · {formatDate(v.created_at)}
                    {v.superseded_at && <> – replaced {formatDate(v.superseded_at)}</>}
                    {reviewLabel(origin, v) && <> · {reviewLabel(origin, v)}</>}
                  </div>
                  <VersionBody layer={layer} version={v} />
                </div>
              ))}
            </details>
          )}
        </>
      )}
    </div>
  );
}

export default function BillLayers({ layers, hasStaffAnalysis, fallbackSummary }: Props) {
  return (
    <>
      {LAYER_ORDER.map((layer) => {
        const meta = LAYER_META[layer];
        const headingId = `layer-${layer}`;
        const says = layer === "bill_says" ? layers.bill_says[0]?.current : undefined;
        const showFallback =
          layer === "bill_says" && fallbackSummary && (!says || says.evidence_state === "insufficient_evidence");
        return (
          <section key={layer} aria-labelledby={headingId} className="mt-5">
            <h2 id={headingId} className="text-sm font-semibold text-ledger-900">{meta.title}</h2>
            <p className="text-xs text-slate-500">{meta.definition}</p>
            {ORIGINS_FOR_LAYER[layer].map((origin) => (
              <Block
                key={origin}
                layer={layer}
                origin={origin}
                block={layers[layer].find((b) => b.origin === origin)}
                hasStaffAnalysis={hasStaffAnalysis}
              />
            ))}
            {showFallback && (
              <div className="mt-2 text-sm text-slate-700">
                <p className="text-xs font-medium text-slate-500">AI summary of the official description</p>
                <p className="mt-0.5">{fallbackSummary}</p>
              </div>
            )}
          </section>
        );
      })}
    </>
  );
}
```

- [ ] **Step 7: Run and confirm pass**

`cd frontend && npx vitest run components/BillLayers.test.tsx && npx tsc --noEmit`. Expected: 9 passed; typecheck clean. (If `SourceOut` in `lib/types.ts` lacks a field used in the test fixture, such as `publisher`, match the fixture to the real interface; don't widen the interface.)

- [ ] **Step 8: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/layers.ts frontend/components/BillLayers.tsx frontend/components/BillLayers.test.tsx
git commit -m "Add BillLayers component with single label lookup and review labels"
```

---

### Task 10: Bill page and methodology page

**Files:**
- Modify: `frontend/app/bills/[id]/page.tsx` (lines 84–96: the "What it does" and "Who it affects" sections)
- Modify: `frontend/app/methodology/page.tsx`
- Test: `frontend/app/methodology/page.test.tsx` (new)

**Interfaces:**
- Consumes: `BillLayers` default export and `hasAnyLayer` (Task 9).

- [ ] **Step 1: Write the failing methodology test**

`frontend/app/methodology/page.test.tsx`:
```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import MethodologyPage from "./page";

describe("MethodologyPage", () => {
  it("explains the three layers and the review labels", () => {
    render(<MethodologyPage />);
    expect(screen.getByRole("heading", { name: "Bill Says, Interpretation, Expected Effect" })).toBeInTheDocument();
    expect(screen.getByText(/checked word for word/)).toBeInTheDocument();
    expect(screen.getByText(/reviewed by a person/)).toBeInTheDocument();
    expect(screen.getByText(/Not yet evaluated/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run and confirm failure**

`cd frontend && npx vitest run app/methodology/page.test.tsx`. Expected: FAIL, heading not found.

- [ ] **Step 3: Add the methodology section**

In `frontend/app/methodology/page.tsx`, insert this section after the "How summaries are written" section:
```tsx
      <section className="mt-6">
        <h2 className="text-base font-semibold text-ledger-900">Bill Says, Interpretation, Expected Effect</h2>
        <p className="mt-2 text-sm text-slate-700">
          Bill pages separate three kinds of statement so you always know which one you are reading.
        </p>
        <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
          <li>
            <span className="font-medium">Bill Says</span> — quotes from the bill itself. An AI model picks the
            provisions, but every quote is checked word for word against the bill text, and any quote that doesn&apos;t
            match is thrown out.
          </li>
          <li>
            <span className="font-medium">Interpretation</span> — what the change means. Where Florida legislative
            staff have published an analysis, their reading is shown first, condensed by AI and labeled with the
            committee and date. Sunshine Ledger&apos;s own AI interpretation of the bill text is shown separately and
            labeled as such, with the assumptions it depends on.
          </li>
          <li>
            <span className="font-medium">Expected Effect</span> — what may happen. These are forecasts, not facts,
            and not legal or financial advice. Staff fiscal findings are restated as staff wrote them, including
            &ldquo;none&rdquo; or &ldquo;indeterminate&rdquo;. Sunshine Ledger only describes effects that a
            specific section of the bill creates; each must cite that section and use words like &ldquo;may&rdquo;
            or &ldquo;could&rdquo;, or it is not published.
          </li>
        </ul>
        <p className="mt-2 text-sm text-slate-700">
          Every AI-written block says whether it has been reviewed by a person. A new version starts unreviewed,
          even if the one it replaced was reviewed. Earlier versions stay visible on the page rather than being
          silently rewritten.
        </p>
        <p className="mt-2 text-sm text-slate-700">
          <span className="font-medium">Not yet evaluated</span> means we haven&apos;t analyzed that part yet — not
          that there is nothing to find. <span className="font-medium">Insufficient evidence</span> means we looked,
          within the scope stated, and couldn&apos;t support a statement.
        </p>
      </section>
```

- [ ] **Step 4: Wire the bill page**

In `frontend/app/bills/[id]/page.tsx`:
- Add imports: `import BillLayers from "@/components/BillLayers";` and `import { hasAnyLayer } from "@/lib/layers";`
- Replace the two sections at lines 84–96 ("What it does" and "Who it affects") with:
```tsx
      {hasAnyLayer(bill.layers) ? (
        <BillLayers layers={bill.layers} hasStaffAnalysis={bill.has_staff_analysis} fallbackSummary={bill.what_it_does} />
      ) : (
        <>
          {bill.what_it_does && (
            <section className="mt-5">
              <h2 className="text-sm font-semibold text-ledger-900">What it does</h2>
              <p className="mt-1 text-sm leading-relaxed text-slate-700">{bill.what_it_does}</p>
            </section>
          )}

          {whoItAffects && (
            <section className="mt-4">
              <h2 className="text-sm font-semibold text-ledger-900">Who it affects</h2>
              <p className="mt-1 text-sm leading-relaxed text-slate-700">{whoItAffects}</p>
            </section>
          )}
        </>
      )}
```

- [ ] **Step 5: Run the full frontend suite and typecheck**

`cd frontend && npx vitest run && npx tsc --noEmit`. Expected: all pass, typecheck clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/bills/[id]/page.tsx frontend/app/methodology/page.tsx frontend/app/methodology/page.test.tsx
git commit -m "Show bill layers on bill pages and explain them on the methodology page"
```

---

### Task 11: Runbook, merge, deploy and rollout

**Files:**
- Modify: `docs/RUNBOOK.md`

This task changes production. Every numbered step that touches production needs the user's go-ahead in the session.

- [ ] **Step 1: Runbook section**

Add to `docs/RUNBOOK.md` after the "Scheduled ingestion" section:
````markdown
## Bill page layers (Bill Says / Interpretation / Expected Effect)

Design: `docs/superpowers/specs/2026-09-23-bill-layers-design.md`.

- Nightly step `bill_layers_batch --limit 150` in `run-ingestion.sh`. Only
  blocks whose inputs changed are regenerated; each change inserts a new
  version and never edits an old one.
- Preview what would run: `docker exec sunshineledger-backend-1 python -m app.pipeline.bill_layers_batch --dry-run --limit 20`
- Quality report (writes nothing): `docker exec sunshineledger-backend-1 python -m app.pipeline.review_bill_layers --sample 20 > layers-review.md`
- Review queue (admin auth, same as flags):
  ```bash
  curl -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" https://sunshineledger-api.josephbernal.com/bill-layers/admin/unreviewed?limit=20
  curl -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" -X POST -H 'Content-Type: application/json' \
    -d '{"decision":"approved"}' https://sunshineledger-api.josephbernal.com/bill-layers/admin/<id>/review
  ```
- Bumping a value in `METHOD_VERSIONS` (`app/pipeline/bill_layers.py`)
  re-versions every block of that kind over the following nights, and
  every new version starts "not reviewed". Don't bump for typo fixes.
````

- [ ] **Step 2: Full test suites**

`./scripts/run-tests.sh` and `cd frontend && npx vitest run && npx tsc --noEmit`. Expected: all green.

- [ ] **Step 3: Merge and push (user go-ahead)**

```bash
git add docs/RUNBOOK.md && git commit -m "Runbook: bill page layers"
git fetch gitea && git switch main && git merge --ff-only gitea/main
git merge --no-ff feature/bill-layers -m "Merge branch 'feature/bill-layers'"
git push gitea main && git push github main && git branch -d feature/bill-layers
```

- [ ] **Step 4: Migrate first, then deploy (user go-ahead)**

The new backend code queries `bill_layers`, so migrate before deploying:
```bash
C=(docker --context sunshine-vm compose -p sunshineledger -f docker-compose.yml --env-file .env)
"${C[@]}" build backend && "${C[@]}" run --rm backend alembic upgrade head
./scripts/deploy.sh
```
Expected: `b3c8e2f41a90 (head)`; the smoke test passes. No bill has layer rows yet, so pages look unchanged.

- [ ] **Step 5: Extraction spot-check in production (read-only)**

Run Task 2 step 5's command. Expected: effect ≥ 90%, fiscal ≥ 85%.

- [ ] **Step 6: Quality gate (read-only), then user sign-off**

```bash
docker --context sunshine-vm exec sunshineledger-db-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from bill_layers"'
docker --context sunshine-vm exec sunshineledger-backend-1 python -m app.pipeline.review_bill_layers --sample 20 > /private/tmp/layers-review.md
docker --context sunshine-vm exec sunshineledger-db-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from bill_layers"'
```
Expected: both counts are `0`. Give the user the report and wait for sign-off. If quality is poor, fix the prompts, bump `METHOD_VERSIONS`, and rerun this step before going on.

- [ ] **Step 7: Browser check on the local stack**

Start a local stack on Docker Desktop (never the `sunshine-vm` context). `docker-compose.override.yml` applies automatically there and adds hot reload:
```bash
# Shell values override .env, so the local frontend talks to the local API,
# never production.
INTERNAL_API_URL=http://backend:8000 NEXT_PUBLIC_API_URL=http://localhost:8010 \
  docker --context desktop-linux compose -p sl-local up -d --build
docker --context desktop-linux compose -p sl-local exec backend alembic upgrade head
docker --context desktop-linux compose -p sl-local exec backend python -m app.pipeline.seed
```
Seed layer rows on the first seeded bill:
```bash
docker --context desktop-linux compose -p sl-local exec -T backend python - <<'EOF'
from datetime import datetime, timezone
from app.db import SessionLocal
from app.models import Bill, BillLayerReview, Entity, Source
from app.pipeline.bill_layers import LayerResult
from app.pipeline.bill_layers_store import store_layer_version

db = SessionLocal()
e = db.query(Entity).join(Bill, Bill.entity_id == Entity.id).first()
src = lambda: [Source(url="https://example.com/doc.pdf", source_type="fl_staff_analysis", retrieved_at=datetime.now(timezone.utc))]
item = lambda t, **k: {"text": t, "section_ref": "Section 1", "quote": k.get("quote"), "assumptions": k.get("assumptions", []), "affected_groups": k.get("groups", [])}
store_layer_version(db, bill_entity_id=e.id, layer="bill_says", origin="bill_text", input_hash="l1", generated_by="llm:local", sources=src(),
    result=LayerResult("supported", "Bill text", [dict(item("This act shall take effect July 1, 2027.", quote="This act shall take effect July 1, 2027."))]))
staff = store_layer_version(db, bill_entity_id=e.id, layer="interpretation", origin="legislative_staff", input_hash="l2", generated_by="llm:local", sources=src(),
    result=LayerResult("supported", "Staff analysis, Rules, 2026-03-01", [item("Staff say section 1 removes a requirement.")]))
db.add(BillLayerReview(bill_layer_id=staff.id, decision="approved", reviewer="local")); db.commit()
store_layer_version(db, bill_entity_id=e.id, layer="interpretation", origin="sunshine_ledger_ai", input_hash="l3", generated_by="llm:local", sources=src(),
    result=LayerResult("supported", "Bill text", [item("Older reading.")]))
store_layer_version(db, bill_entity_id=e.id, layer="interpretation", origin="sunshine_ledger_ai", input_hash="l4", generated_by="llm:local", sources=src(),
    result=LayerResult("supported", "Bill text", [item("Removes a requirement.", assumptions=["Agencies comply"], groups=["State employees"])]))
store_layer_version(db, bill_entity_id=e.id, layer="expected_effect", origin="sunshine_ledger_ai", input_hash="l5", generated_by="llm:local", sources=src(),
    result=LayerResult("insufficient_evidence", "No effects traceable to a specific bill section", []))
print(e.id)
EOF
```
Open `http://localhost:3010/bills/<printed id>` in Chrome (browser automation), resize to 375px width, and check:
- heading order Bill Says → Interpretation → Expected Effect
- badge and review text for all four states: reviewed staff, unreviewed AI, insufficient evidence, and "No staff analysis published" / "Not yet evaluated"
- "1 earlier version" opens with the keyboard
- no horizontal scroll
- labels are readable with styles ignored

Record a GIF (`bill_layers_mobile_check.gif`). Tear down afterwards with `docker --context desktop-linux compose -p sl-local down -v`.

- [ ] **Step 8: Backfill (user go-ahead)**

```bash
docker --context sunshine-vm exec sunshineledger-backend-1 python -m app.pipeline.bill_layers_batch --limit 25
```
Check two or three of the bills on the live site, then continue with larger `--limit` runs on later nights. After that, copy `scripts/run-ingestion.sh` to docker-host (as `joe@docker-host`, e.g. `! ssh docker 'cp -p ~/scripts/run-ingestion.sh ~/scripts/run-ingestion.sh.bak-<date>'` followed by the `curl` from the GitHub raw URL) so the nightly step takes over.

- [ ] **Step 9: Close out**

Comment on Todoist `6hX5mHjFXJQ4R3pp` with the commits, test results and backfill status. Close it when the backfill is complete.
