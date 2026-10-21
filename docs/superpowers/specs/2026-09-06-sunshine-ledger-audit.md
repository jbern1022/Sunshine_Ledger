# Sunshine Ledger — Project Audit
**Date:** 2026-09-06
**Auditor:** Claude (parallel agent session)

---

## 1. Project Overview

**What it is:** Sunshine Ledger is a Florida civic-intelligence / legislation tracker — NOT a personal finance app. The name references Florida's Sunshine Law (public records). It shows plain-language AI summaries of state and local bills, an interactive geographic impact map, legislator sponsorship data, roll-call votes, and GDELT news associations.

**Core thesis:** Make Florida legislative data legible to ordinary citizens by combining structured government records with LLM-generated plain-language summaries and geographic context.

**Current status: Late MVP / Early Production.** All 10 roadmap MVP steps are implemented. The app is publicly live at `sunshineledger.josephbernal.com`. The codebase shows evidence of real operation: documented production incidents (4-night ingestion failure Aug 21-24, 0-byte backup Aug 21, column overflow crash), migrations applied to fix live issues, and a verified database restore (2,311 bills, 4,240 claims as of Aug 4).

**Stack:**
- Backend: Python/FastAPI + PostgreSQL/PostGIS
- Frontend: Next.js 16 / TypeScript / Tailwind
- LLM: Ollama `llama3.1:8b` on homelab GPU (Omen)
- Deployment: Docker Compose on Proxmox VM, Cloudflare Tunnel for public exposure

---

## 2. Notion Inspection

**Result: Unable to assess** (Notion MCP permissions denied in subagent session).

**Codebase evidence of documentation gaps:**
- BRD, Project Charter, and Phased Roadmap exist only as `.docx` files in `docs/`. If Notion is the living knowledge base, these should be imported or linked.
- No sprint tracking, design decision records, or open issue lists could be confirmed in Notion.
- The election calendar re-verification schedule (`verify_by = 2026-10-15`) exists only as a code comment — should be a calendar event or Notion reminder.

---

## 3. Todoist Inspection

**Result: Unable to assess via subagent.** Reconciliation performed by main session after audit. Based on codebase evidence, the following tasks were expected to exist or be created:

Codebase-implied existing tickets:
- Powerstation DHCP reservation (referenced in RUNBOOK)
- Uptime Kuma push monitor setup (referenced in RUNBOOK)
- Miami iQM2 attachment ingestion (blocked by PII risk — referenced in code)
- Activate Woodpecker CI (`.woodpecker.yml` complete but not registered)

Codebase-implied missing tickets (not previously tracked):
- Full-text summarization swap (`summarize.py` reads `bill.description` not `bill.full_text`)
- `(bill_entity_id, claim_type)` uniqueness constraint migration
- Bill list COUNT query performance fix
- Ingestion log rotation
- District map click-through to sponsor-filtered bill list

---

## 4. Codebase Audit

### 4a. Security

**Secrets handling:**
- Environment variables used throughout — no hardcoded credentials found in source
- `.env.example` pattern present — good baseline
- Cloudflare Tunnel credentials: managed via Cloudflare dashboard, not in repo — correct

**Input validation:**
- FastAPI with Pydantic models provides baseline validation on API inputs
- Bill entity IDs and legislator IDs come from government sources — low injection risk
- No user-generated content beyond read-only public API — low XSS surface

**API security:**
- No rate limiting on public API endpoints — a concern if the app grows
- CORS configuration: not confirmed as restrictive
- No authentication on API (it's a public read-only API — appropriate for current scope)

**Assessment:** Security posture is acceptable for a public read-only civic data app. The main gap is rate limiting, which matters at scale.

### 4b. Data Model & Backend

**P0: Monitoring infrastructure built but not activated**
`scripts/monitoring.sh` and `monitoring.env.example` implement Uptime Kuma push monitors. However, `monitoring.env` has never been created on Omen with real push URLs. Every heartbeat ping is a silent no-op. Two real outages (4-night ingestion failure Aug 21-24, 0-byte backup Aug 21) went undetected until manual log inspection. The monitoring code is complete — it just needs the env file created.

**P1: No DB-level uniqueness constraint on `(bill_entity_id, claim_type)` in `claims` table**
The pipeline manages deduplication via `input_hash` logic, but nothing at the database level prevents two `what_it_does` claims for the same bill. A hash-check bug or concurrent ingestion run would silently accumulate duplicates. The API's `_what_it_does()` helper takes the first match — silently and potentially inconsistently.

**Fix:** `ALTER TABLE claims ADD CONSTRAINT uq_claim_type UNIQUE (bill_entity_id, claim_type);`

**P1: Bill list `total` count loads full result set into Python**
`list_bills` uses `len(db.execute(stmt).scalars().all())` to count matching rows. At 2,300 bills this is acceptable. The BRD explicitly targets nationwide scale (150,000+ bills). At that scale, this query loads the entire result set into memory on every paginated request.

**Fix:** Replace with `SELECT COUNT(*) FROM (...) subquery` or SQLAlchemy `func.count()`.

**P1: Full-text summarization swap is unfinished**
`pipeline/bill_text.py` fetches and stores `bill.full_text`. But `summarize.py` still reads from `bill.description` (the short official blurb). All the infrastructure for the swap exists: `bill_text.py`, `review_summaries.py`, `input_hash` caching. The actual read-from-full-text change in `summarize.py` has not been made. Bills are being summarized from truncated descriptions rather than the full text.

**P2: Ingestion pipeline has no retry logic for transient failures**
The 4-night ingestion failure (Aug 21-24) was caused by a network or API timeout. The pipeline exits on failure with no retry. Adding exponential backoff retry for transient errors and alerting on persistent failure would prevent silent multi-day gaps.

**P2: No migration tool / schema versioning**
Schema changes have been applied manually. No Alembic or Flyway. As the schema evolves, manual migrations become error-prone and harder to reproduce on a fresh environment.

### 4c. Frontend / UX

**What's implemented:**
- Bill list with search and filters (status, chamber, sponsor)
- Bill detail page with AI summary, full text, legislator info, roll-call votes
- Geographic impact map (PostGIS-backed)
- Legislator pages with sponsored bills

**Missing UI states:**
- Loading skeletons not confirmed on all views
- Empty state handling (e.g., bill with no summary yet, district with no bills) — not confirmed as graceful

**P2: District map click-through to sponsor-filtered bill list**
A `// TODO` comment in `MapView.tsx` flags this: clicking a district on the map should filter the bill list to bills affecting that district/legislator. This is the most natural user interaction on the map and it's not wired up.

**P2: No pagination controls confirmed on bill list**
The API supports pagination (`limit`, `offset`). Whether the frontend exposes pagination controls for navigating beyond the first page is not confirmed.

**P3: Mobile responsiveness**
Not assessed in detail. A civic data app with map and table views requires careful responsive design. The map in particular (PostGIS-backed, likely Leaflet or Mapbox) needs explicit mobile treatment.

### 4d. Testing

**CI pipeline status:**
- `.woodpecker.yml` is comprehensive: backend pytest with PostGIS service container, frontend Vitest + build step
- The file's own header states the repo is NOT registered with the Woodpecker server yet
- Every push runs no automated tests

**What's tested:** Backend pytest suite is defined. Coverage level not confirmed from audit.

**Critical paths to test:**
- Bill ingestion pipeline (end-to-end from API fetch to DB write)
- LLM summarization with mock Ollama (test the pipeline logic, not the model)
- `list_bills` pagination and filter correctness
- Uniqueness constraint behavior on duplicate ingestion

### 4e. Operations

**Backup:**
- Volume backups exist (referenced in RUNBOOK and incident log)
- 0-byte backup incident occurred Aug 21 — backup script has a failure mode that produces an empty file silently
- No backup validation step (restore test): the only time you know a backup works is when you need it

**Deployment:**
- Docker Compose on Proxmox VM via Cloudflare Tunnel
- No documented rollback procedure for a bad deploy
- Database migrations applied manually — no automated migration on deploy

**Log access:**
- All logs are local to the container on Omen
- No centralized log collection — debugging requires SSH + docker logs
- Ingestion failures invisible until manual inspection

---

## 5. Prioritized Roadmap

### Track 1: Operations & Reliability

**P0: Create `monitoring.env` on Omen with real Uptime Kuma push URLs**
- **What:** Click through Uptime Kuma UI, create two push monitors (ingestion pipeline, app availability), copy the push URLs into `monitoring.env` on Omen. The script is already written.
- **Why:** Two real outages went undetected for days. The monitoring code is done. This is a 15-minute task that prevents the next undetected outage.

**P1: Activate Woodpecker CI — register repo and run the pipeline**
- **What:** Register the Sunshine Ledger repo with the Woodpecker server. The `.woodpecker.yml` pipeline is complete and ready.
- **Why:** Every push currently runs no tests. The pipeline already handles pytest with PostGIS service container and Vitest frontend build — it just needs to be activated.

**P1: Fix backup validation — add restore test and non-zero check**
- **What:** Add a post-backup step that: (1) checks the backup file is non-zero bytes, (2) attempts a test decompress, (3) alerts via ntfy if either check fails.
- **Why:** The Aug 21 incident produced a 0-byte backup silently. The next disk failure or DB corruption event will have no valid backup to restore from if this isn't caught.

**P2: Add ingestion retry logic for transient failures**
- **What:** Wrap API fetch calls in exponential backoff retry (3 attempts, 30/60/120s). Alert via ntfy after all retries exhausted.
- **Why:** The 4-night outage was caused by a transient failure with no retry. A single retry would have recovered automatically.

**P2: Add Alembic for schema migrations**
- **What:** Initialize Alembic, write the current schema as the baseline migration, document the migration workflow.
- **Why:** Manual schema changes are not reproducible and can't be automated on deploy. Alembic enables `alembic upgrade head` as part of the deploy process.

### Track 2: Data Integrity

**P1: Add `(bill_entity_id, claim_type)` uniqueness constraint to `claims` table**
- **What:** `ALTER TABLE claims ADD CONSTRAINT uq_claim_type UNIQUE (bill_entity_id, claim_type);`
- **Why:** Nothing prevents duplicate claims at the DB level. A pipeline bug or concurrent run would silently accumulate duplicates that the API resolves by taking the first match — inconsistently.

**P1: Fix bill list `total` count — replace Python `len()` with SQL `COUNT(*)`**
- **What:** Replace `len(db.execute(stmt).scalars().all())` with a proper `SELECT COUNT(*)` query.
- **Why:** At 2,300 bills this is invisible. At the BRD's nationwide target (150,000+ bills), this loads the entire result set into memory on every paginated API request.

**P1: Complete full-text summarization swap in `summarize.py`**
- **What:** Change `summarize.py` to read from `bill.full_text` instead of `bill.description`. The `bill_text.py` fetch pipeline, `input_hash` caching, and `review_summaries.py` quality gate are all ready.
- **Why:** Bills are currently summarized from a short official blurb. The full text contains the actual legislative language that makes summaries accurate and useful.

### Track 3: Features

**P2: Wire district map click-through to sponsor-filtered bill list**
- **What:** The `// TODO` in `MapView.tsx` — clicking a district filters the bill list to that district's bills/legislator.
- **Why:** This is the most natural interaction on the map and is currently unimplemented. A map that shows geographic impact but can't drill down is half-finished.

**P2: Verify pagination controls are exposed in frontend bill list**
- **What:** Confirm the frontend renders pagination UI (next/prev, page number) for navigating beyond the first page of results.
- **Why:** The API supports pagination; if the frontend doesn't expose it, users see only the first N bills.

**P3: Miami iQM2 attachment ingestion**
- **What:** Pipeline to ingest Miami City Commission meeting attachments via iQM2. Currently blocked on PII risk assessment.
- **Why:** Expands Sunshine Ledger beyond state bills to local government — the core local government accountability use case.

### Track 4: API & Performance

**P2: Add rate limiting to public API endpoints**
- **What:** Add `slowapi` or nginx-level rate limiting: e.g., 100 req/min per IP on `/bills` list endpoints.
- **Why:** Currently no protection against scraping or runaway clients. Not urgent at current traffic but needed before any significant public exposure.

**P2: Add database indexes for common query patterns**
- **What:** Audit slow query log (once monitoring is active) for missing indexes. Priority candidates: `bills.status`, `bills.chamber`, `claims.bill_entity_id`, `legislators.district_id`.
- **Why:** As the dataset grows, unindexed columns in filter-heavy list queries will degrade linearly.

### Track 5: Documentation

**P1: Import BRD and Phased Roadmap from `.docx` to Notion (or link from README)**
- **What:** Make the BRD and roadmap living documents in Notion, or at minimum link them clearly from the README.
- **Why:** `.docx` files in a git repo are hard to navigate, unsearchable in Notion, and not linked from anywhere in the codebase.

**P2: Add election calendar re-verification as a Notion reminder / calendar event**
- **What:** The code has `verify_by = 2026-10-15` as a comment. Create a Notion reminder or Google Calendar event to verify election calendar data before that date.
- **Why:** A code comment is not a reliable reminder system.

---

## 6. Priority Sequence

| Priority | Action |
|---|---|
| P0 | Create `monitoring.env` on Omen — activate push monitors |
| P1 | Activate Woodpecker CI (register repo) |
| P1 | `(bill_entity_id, claim_type)` uniqueness constraint |
| P1 | Fix bill list `total` COUNT query |
| P1 | Complete full-text summarization swap |
| P1 | Backup validation (non-zero check + restore test) |
| P1 | Import BRD/roadmap to Notion |
| P2 | Ingestion retry logic |
| P2 | Alembic schema migrations |
| P2 | District map click-through |
| P2 | Verify pagination in frontend |
| P2 | Rate limiting on public API |
| P2 | DB indexes for common query patterns |
| P2 | Add election calendar reminder |
| P3 | Miami iQM2 attachment ingestion |

---

## 7. Biggest Risk

**Monitoring is built but not active — the next outage will be invisible, just like the last two.**

The monitoring code is complete. Uptime Kuma is running. `scripts/monitoring.sh` and `monitoring.env.example` are in the repo. The only missing step is creating `monitoring.env` on Omen with real push URLs from the Uptime Kuma UI.

The Aug 21-24 ingestion failure went undetected for four nights. The 0-byte backup on Aug 21 went undetected until the restore was needed. Both would have been caught immediately with functioning monitors. This is a 15-minute fix that prevents the next silent multi-day outage.
