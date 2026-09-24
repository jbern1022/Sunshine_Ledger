# Bill Layers Quality Round Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fix the problems the 2026-09-23 quality-gate report found before any bill layer goes public: garbled bill text (leftover line numbers; struck and added wording flattened together), wrong Bill Says section numbers, duplicate quotes, contradictory staff fiscal findings, Sunshine Ledger Expected Effect that only restates provisions, and timeouts. Also allow a separate, larger model for the layers.

**Architecture:** Bill text is re-extracted with inline change markers, `[deleted: …]` and `[added: …]`. Senate HTML carries them as `<s class="Remove">` / `<u class="Insert">`. House PDFs draw them as lines, which pdfplumber can locate: a line through a word's middle means deleted, a line under it means added. Line numbers sit in the PDF's left margin and are dropped by position. The marked text is stored in `bills.full_text`. Summaries read it as-is. Bill Says reads a derived "law as amended" view: deletions dropped, additions unwrapped.

**Tech Stack:** FastAPI/SQLAlchemy/pytest backend, pdfplumber (new dependency), BeautifulSoup, Ollama.

**Spec:** `docs/superpowers/specs/2026-09-23-bill-layers-design.md`. The decisions below, taken with the user on 2026-09-23 after the quality-gate report, amend it.

## Decisions (binding)

1. Stored `full_text` keeps deletions as `[deleted: …]` and marks additions as `[added: …]`. Summaries read the marked text; Bill Says quotes the law-as-amended view.
2. Sunshine Ledger Expected Effect is reworked, not dropped: new prompt (consequences, not provisions) plus a restatement guard.
3. Layers get their own model setting, `OLLAMA_LAYERS_MODEL` (defaults to `OLLAMA_MODEL`). The next quality report compares `llama3.1:8b` and `qwen2.5:14b`. Summaries stay on `OLLAMA_MODEL`.

## Global Constraints

- Work on branch `feature/bill-layers-quality` in a worktree (never on local `main`). Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` after a blank line. Never use `git stash`. Never touch the `sunshine-vm` docker context in implementation tasks.
- Backend tests: `docker --context desktop-linux compose -f docker-compose.test.yml run --rm backend-test sh -c "pip install -q -r requirements-dev.txt && pytest tests/<file>.py -v"; docker --context desktop-linux compose -f docker-compose.test.yml down -v`. Full suite: `./scripts/run-tests.sh`. Baseline: 359 passed, 1 pre-existing warning.
- Marker syntax, exactly: `[deleted: <text>]` and `[added: <text>]`. Consecutive marked words of the same kind merge into one marker. Whitespace inside markers is single spaces.
- Fixtures (real public records, already committed on this branch): `backend/tests/fixtures/bill_text/h0565_enrolled.pdf` and `s0564_c1.html`.
- Known ground truth:
  - **H0565 enrolled:** "managers and supervisors" is struck; "Tatton-Brown-Rahman syndrome" and "all employees" are underlined; the word before ", or Tatton-Brown-Rahman" ("or") is struck. The text must not contain "Phelan-32" or any left-margin line numbers.
  - **S0564 c1:** the struck word is "No" (in "An No agency"); there are 17 `class="Insert"` spans.
- Summaries: bump `summarize.PROMPT_VERSION` to "2", and add one sentence to both summary prompts explaining the markers. Re-summarizing everything is intended.
- No `METHOD_VERSIONS` bumps are needed, because no layer rows exist in production. Bump them anyway if a prompt changes, so the hashes stay truthful.

---

### Task 1: Marked text extraction (HTML + PDF) and line-number fix

**Files:** modify `backend/app/pipeline/bill_text.py`, `backend/requirements.txt` (add a pinned `pdfplumber`); test `backend/tests/test_bill_text_markers.py`.

**Build:**
- `html_to_marked_text(html: str) -> str`: before text extraction, replace every element with class `Remove` (any tag) with `[deleted: <its text>]`, and every element with class `Insert` with `[added: <its text>]`. Then run the existing `clean_html_legislative_text`. `extract_html_text` uses it.
- `mark_words(words, segments, *, margin_x=60.0) -> list[str]`: a pure function over pdfplumber-style dicts. `words` have `text, x0, x1, top, bottom`; `segments` are thin horizontal lines/rects with `x0, x1, top, bottom`.
  - Group words into text lines by `top`, within 2pt.
  - Drop numeric-only words with `x0 < margin_x` (left-margin line numbers).
  - A word is **deleted** if a segment overlaps it horizontally at its vertical middle (±2.5pt). It is **added** if a segment runs along its bottom (0–3pt below `bottom`).
  - Merge runs of the same kind into one marker, and return one string per text line.
- `extract_pdf_text(pdf_bytes)`: use pdfplumber plus `mark_words`, then drop page furniture with the existing `_BOILERPLATE` patterns. That includes the "CODING: Words stricken are deletions; words underlined are additions." legend line, so the legend's own "stricken"/"underlined" words never become markers. If pdfplumber fails on a document, log it and fall back to the pypdf path.
- `clean_legislative_text` (pypdf fallback and Legistar): make trailing line-number detection accept a number glued to a hyphen (`Phelan-32` → `Phelan-`), and resync the sequence when the next number is 1–3 ahead of expected.

**Tests:**
- HTML fixture → contains `An [deleted: No] agency` and at least one `[added: `; no raw tags.
- PDF fixture → contains `[deleted: managers and supervisors]` and `[added: Tatton-Brown-Rahman syndrome` (it may continue); contains no `Phelan-32`; contains no line that is only a number; contains no `CODING`.
- `mark_words` unit tests: a strike-through, an underline, run merging, margin-number dropping.
- `clean_legislative_text` tests: the hyphen case and resync.

### Task 2: Law-as-amended view, section fixes, deduplication

**Files:** modify `backend/app/pipeline/bill_layers_text.py` and `backend/app/pipeline/bill_layers.py`; tests in the existing `test_bill_layers_text.py` and `test_bill_layers_generate.py`.

**Build:**
- `law_as_amended(text) -> str`: remove `[deleted: …]` entirely, unwrap `[added: X]` to `X`, collapse double spaces.
- `_BILL_SECTION`: a heading is `Section N.` **not** followed by a digit (e.g. "Section 316.1895" is not a heading), case-insensitive.
- `build_bill_says`:
  - The model sees, and quotes are verified against, `law_as_amended(truncated text)`.
  - `section_for_quote` runs on that same view.
  - Drop duplicate quotes (same normalized text).
  - Update the prompt to say the text is the law as it will read.
- `build_ai_interpretation` and `build_ai_expected_effect` see the marked text, with the marker sentence added to their prompts (see Task 4 for Expected Effect). The section-existence guard uses `law_as_amended`.
- Bump the relevant `METHOD_VERSIONS`.

**Tests:**
- `law_as_amended` cases.
- The heading regex rejects `Section 316.1895, F.S.` at line start.
- A duplicate quote is dropped.
- A Bill Says quote containing added text verifies against the amended view, and a quote containing deleted words is dropped.

### Task 3: Summaries read marked text

**Files:** modify `backend/app/pipeline/summarize.py`; tests in the existing summarize tests.

**Build:** `PROMPT_VERSION = "2"`. Add to both summary prompts: "In the text, [deleted: …] marks wording the bill removes and [added: …] marks wording it adds; describe the change, not the markers." Also add a test that the prompts contain the sentence and that the hash changes with the version.

### Task 4: Staff Expected Effect deduplication and Sunshine Ledger Expected Effect rework

**Files:** modify `backend/app/pipeline/bill_layers.py` and `bill_layers_text.py`; tests.

**Build:**
- **Staff Expected Effect:**
  - The prompt asks each item for a `category`: one of `tax_fee`, `state_government`, `local_government`, `private_sector`, `other`.
  - Code keeps the first item per category, except `other`.
  - For a category where staff checked one option out of a printed list ("None / Indeterminate / Insignificant"), the prompt tells the model to report only the option staff selected. If the fiscal text lists all options with no clear selection, the item is dropped by the dedupe (first wins) — accept that.
- **Sunshine Ledger Expected Effect:**
  - New prompt: describe consequences for people or institutions that follow from a provision. Do not restate the provision. Each item still cites its section.
  - New guard, `restates_bill(statement, text) -> bool`: true when `difflib.SequenceMatcher` ratio ≥ 0.6 against any sentence of `law_as_amended(text)` of similar length. It must be efficient: compare only sentences sharing ≥ 3 content words.
  - Items that restate are dropped.
  - The conditional-wording check stays, but "may not" alone doesn't count.
  - Bump `METHOD_VERSIONS`.

**Tests:**
- An item that copies a bill sentence with "may" inserted is dropped.
- A genuine consequence item is kept.
- "X may not do Y" copied from the bill is dropped.
- Staff dedupe keeps one per category.

### Task 5: Layers model setting, timeout and retry

**Files:** modify `backend/app/config.py`, `backend/app/pipeline/summarize.py` (OllamaClient), `bill_layers_batch.py` and `review_bill_layers.py`; tests.

**Build:**
- `settings.ollama_layers_model` (env `OLLAMA_LAYERS_MODEL`, default = `ollama_model`).
- `OllamaClient(timeout: float = 120.0)`. `generate` retries once on `httpx.TransportError`, not on HTTP status errors.
- The batch and the review script build `OllamaClient(model=settings.ollama_layers_model, timeout=300)`.
- The review script gets `--model` (overrides) and `--bills-from <report.md>`, which reuses the bill numbers from an earlier report so two models run on the same bills. The report header names the model.

**Tests:** default and env override of the setting; one retry on `ConnectError` then success; no retry on a 404.

---

## After the tasks (controller, with user go-ahead each)

1. Merge, push, deploy. There are no migrations; `pdfplumber` goes into the image.
2. Re-extract text: `python -m app.pipeline.bill_text --refresh --source legiscan`, then `--source legistar`. Spot-check H0565 and S0564.
3. Quality report twice on the same bills (the 20 from 2026-09-23 plus 20 new): once with `--model llama3.1:8b`, once with `--model qwen2.5:14b`. The user picks the model and signs off.
4. Summaries regenerate through the nightly job (the cap may need raising).
