# Accuracy sample 01: local legislation, "what it does" (2026-11-25)

Method: `SOURCE_TO_CLAIM_AUDIT_TEMPLATE.md`. **First pass, single auditor (Claude), not independent**: an AI
model checking AI-written text. The numbers are a working baseline for fixing defects, **not a publishable
accuracy claim** until a human second auditor re-checks at least 25% of sentences.

| Header | Value |
|---|---|
| Audit id | A-2026-11-25-01 |
| Stratum | Local legislation (city and county ordinances and resolutions) with a generated `what_it_does` |
| Frame | 2,950 records from the public API on 2026-11-26 01:50–02:40 UTC |
| Draw | 20 records, `random.Random(20261125).sample` over the frame sorted by `entity_id` |
| Source checked | Full text where the API has it (6 records); otherwise the official title (14 records). The description the summarizer used for title-only items is **not exposed by the API**, so claims beyond the title are marked **U** (unverified), not wrong. |

## Results

| | Records | Sentences | Critical | Major | U | Uses "bill" for a local instrument (C4, minor) |
|---|---|---|---|---|---|---|
| With full text | 6 | 19 | 0 | 1 | 0 | 3 of 6 |
| Title only | 14 | 38 | 2 | 11 | 10 | 13 of 14 |
| **All** | **20** | **57** | **2** | **12** | **10** | **16 of 20** |

Critical + major: **1 of 19 sentences (5%) with full text; 13 of 38 (34%) title only.** With n this small the
95% upper bounds are wide (about 25% and 50%); read the direction, not the decimals.

## Findings by record

| # | Record | Text? | Finding | Check | Severity |
|---|---|---|---|---|---|
| 1 | Jacksonville 2026-0934 (rezoning) | yes | Accurate; "this bill" | C4 | minor |
| 2 | Miramar R8649 (board appointments) | no | Calls them "advisory boards" and explains what they do; the title says neither | C1/C7 | 2 major |
| 3 | Jacksonville 2026-0578-E (Trinity Rescue Mission $479,997) | yes | Accurate, including the competitive-solicitation exemption | — | — |
| 4 | Jacksonville 2026-0890 (Beach Place PUD) | yes | Accurate, including the 31-day contingency; "this bill" | C4 | minor |
| 5 | Plant City 26-564 (Midtown) | no | "the city giving property to a developer": a "disposition" may be a sale or lease | C2 | major |
| 6 | Ocala 2026-2203 (flood definitions) | no | Glosses "cumulative substantial improvement" as changes that "affect its flood risk" (it is about the value of cumulative improvements) and invents a purpose ("to clarify and standardize") | C2, C7 | 2 major |
| 7 | Key West 26-5904 (sinkhole) | yes | "The City Commission **has ratified**": the resolution is an unnumbered draft; amounts and funds are correct | C2 (status) | major |
| 8 | Miramar R8855 (Caribbean-American Heritage Month) | yes | Accurate; "this bill" | C4 | minor |
| 9 | Key West 26-5958 (USS Key West sail) | no | "tells the City Manager to **buy**": the title says "**pursue procurement**" | C2 (modality) | major |
| 10 | Miami R-26-0321 (DDA millage) | no | Defines the rolled-back rate as "based on previous years' tax rates" (it is the rate that raises the same revenue as last year); says the City Commission holds the hearings (U) | C2 | major + U |
| 11 | Pinecrest VOP2324 (emergency tree removal) | yes | Accurate, including the bidding waiver | — | — |
| 12 | Miami 14477 (traffic studies) | no | Accurate restatement of the title | C4 | minor |
| 13 | Margate 2026-319 (union contract) | no | "a contract between **the state** and the Federation": it is the **City of Margate's** agreement | C2/C6 (wrong party) | **2 critical** |
| 14 | Marco Island 26-5901 (floodplain) | no | Specific reporting duty not in the title (U); invented purpose | C7 | major + U |
| 15 | Miami R-26-0331 ($60,000 DEP grant) | no | "The city … is asking to be allowed to accept": the Commission authorizes its manager to accept if awarded | C2 | major |
| 16 | Plant City 26-492 (affordable-housing inventory) | no | "This bill is a public hearing" | C4 | minor |
| 17 | Hollywood R-2026-293 (fire rescue assessment) | no | Calls a special assessment "a tax" (a legal distinction in Florida); "all properties" (U) | C2 | major + 2 U |
| 18 | Ocala 2027-0361 (police retirement) | no | Describes a pension system as "a plan that helps police officers save" | C2 | major |
| 19 | Hollywood PO-2026-019a (TDR comp-plan amendment) | no | "establish a program" and state "approval" go beyond the title | C1 | 2 U |
| 20 | Doral 26-6703 (rezoning) | no | Acreage, address and districts not in the title; come from the unexposed description | C1 | 3 U |

## Patterns (what to fix, in order)

1. **Title-only records produce most of the errors.** With no text the model fills the gap with definitions,
   purposes and actors (records 2, 6, 13, 14, 17, 18). Fix: for local items without full text, either keep to a
   restatement of the title (the existing `rule:item_title` path) or use a stricter prompt that forbids
   definitions, purposes and parties not in the input, and label the result "Summarized from the official title
   only".
2. **Wrong level of government** (record 13, critical): "the state" for a city. Fix: put the jurisdiction in the
   prompt and reject answers that name "the state" for a local record unless the input does.
3. **Status and modality** (records 7, 9, 15): drafts described as done, "pursue" as "buy". Fix: the layer
   pipeline's modal-strength guard (`overstates_modal`) does not run on `what_it_does`; extend it.
4. **"This bill" for ordinances and resolutions** (16 of 20). The 2026-10-29 fix covered non-legislation only.
   Fix: name the instrument from `item_type` ("This ordinance", "This resolution").
5. **Traceability gap**: for title-only items, the input the summary came from is not shown or exposed. Fix: show
   the description beside the summary, or link it as the source excerpt.

Next: state bills (stratum 2) and local non-legislation (stratum 3); a human second auditor on records 2, 7,
9, 13, 15 and 17 first.
