# Theory of change, outcome metrics and 12-month budget (DRAFT for the owner)

Todoist `6hxjxVQxjWpGh7mp` (W6). Draft 2026-11-25. **Nothing here is approved:** the figures are planning
estimates, not quotes, and the funding ask is a proposal to test against funders' own rules (Gate 6). Built
from the Notion plan "Sustainable Funding, Founder Salary & Critical Pushbacks" (2026-11-13) and the findings in
`PAST_WINNERS_COMPARISON.md` and `FUNDER_SHORTLIST.md`.

## 1. Problem

Florida residents and reporters cannot easily see what a state bill or a local ordinance actually changes, who it
reaches, or how it moved, without reading statutory text and hunting across 30+ separate government portals.
Coverage of the Legislature's local impact is thin outside a few newsrooms.

## 2. Theory of change

| Step | Statement | Evidence we have | Evidence we still need |
|---|---|---|---|
| Inputs | Official records from LegiScan/flsenate.gov, 31 local Legistar sources, Miami iQM2, Congress roll calls; Census/BLS context | Live, nightly, with per-source freshness | Per-source completeness denominators |
| Activities | Source-linked plain-language explanations (what it says, interpretation, expected effect, who it affects) with abstention where the text is silent; correction log | Built and public | Independent accuracy audit |
| Outputs | Bill and ordinance pages a reporter can cite; filed-vs-current text comparison; vote and amendment history | Built | Citation-ready export (W5) |
| Short-term outcome | Reporters and residents find what changed and check the official source faster | **None yet** | Pilot task-completion and time-to-source (W4/W5); source clicks per 100 bill reads (usage counts, once switched on) |
| Medium-term outcome | More local stories cite primary legislative records; fewer errors about what a law does | **None yet** | Partner newsroom case studies; published corrections |
| Long-term impact | Residents can hold state and local officials to what the record shows | n/a | Not claimed in this grant |

Assumptions to state, not hide: readers want source-linked explanations (unvalidated); AI-assisted text can be
kept accurate enough with review and abstention (partially evidenced; audit pending); a single maintainer can
keep 30+ sources current (true today; a single-point-of-failure risk).

## 3. Outcome metrics (12 months)

Each has a baseline method; targets are set **after** the January baseline, not guessed now.

| Metric | Measured by | Baseline available |
|---|---|---|
| Claim accuracy (critical + major errors per 100 sentences, per stratum, with 95% bound) | `SOURCE_TO_CLAIM_AUDIT_TEMPLATE.md`, second auditor on ≥25% | First sample in W2/W3 |
| Source freshness (share of sources checked in the last 36 h, monthly) | `/sources/status` | Yes (33 of 37 fresh on 2026-11-25) |
| Coverage denominators (records with text / records, per source) | `/sources/status` | Yes |
| Pilot task completion and time to find the official source | Structured sessions (W4/W5), 5–10 participants | No |
| Source clicks per 100 bill reads | Usage counts (dark, owner switch) | No |
| Partner use (stories or briefings citing the site, with the partner's permission) | Partner log | No |
| Corrections published and median time to correct | `/corrections` | Yes |

## 4. Two budget scenarios

**A. Prototype-scale project grant (matches the Florida precedents, $25k–$100k).** Twelve months, one partner
newsroom, a defined deliverable: the Legislature's 2027 session explained for South Florida readers, with a
reproducible accuracy audit.

| Line | 12-month estimate | Note |
|---|---|---|
| Founder time, part-time (≈ 0.4 FTE) | $32,000 | At the plan's $80k gross FTE rate; not a salary promise |
| Independent accuracy review (second auditor, 2 rounds) | $6,000 | Gate 3/6 credibility |
| Independent WCAG AA accessibility audit | $5,000 | Plan line; Todoist `6hxjxVMmvfR8HPPG` |
| Cloud and hosting (off-site backups, uptime check, small API host if justified) | $1,800 | Inside the $100/month AWS target (owner-approved 2026-11-16) |
| Data APIs and software | $1,500 | LegiScan tier, domain, tooling |
| Partner newsroom stipend / training | $8,000 | Only if the partner wants it; no endorsement implied |
| Accounting, insurance, legal review of grant terms | $3,000 | Entity question still open |
| Contingency (≈10%) | $5,700 | |
| **Total** | **≈ $63,000** | Add a fiscal sponsor's fee if one is used (often 5–10%; confirm) |

**B. Sustaining budget (the Notion plan, not an ask for a single grant).** $125,000 project spending, about $140,000
gross with a 10% sponsor fee, covering an $80,000 gross founder salary. The plan's own red team says this is "a
financing goal, not a valuation" and needs diversified, committed funding first. Use it only as the long-term
picture in the dossier.

## 5. Owner decisions

1. Scenario A as the first ask, or a different scope?
2. The partner newsroom to approach first (the Florida Trib suggested).
3. Whether founder time is budgeted at all in a first ask, or the ask covers only outside costs (audit,
   accessibility, partner stipend), which is easier to fund while the entity question is open.
