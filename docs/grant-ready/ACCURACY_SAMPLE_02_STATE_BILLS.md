# Accuracy sample 02: 2026 state bills, "what it does" (2026-11-25)

Method: `SOURCE_TO_CLAIM_AUDIT_TEMPLATE.md`. **First pass, single auditor (Claude), not independent.** A working
baseline, not a publishable figure.

| Header | Value |
|---|---|
| Audit id | A-2026-11-25-02 |
| Stratum | Florida 2026 Regular Session bills with a generated `what_it_does` |
| Frame | 1,897 bills from the public API |
| Draw | 20, `random.Random(20261125).sample` over the frame sorted by `entity_id` |
| Source checked | The bill's official title ("An act relating to …; amending …; requiring …"), which lists every provision, and the text where a claim needed it. A detail the title does not cover and that was not found in the text is **U**. |

## Results

| Records | Sentences | Critical | Major | U | "Bill" for a joint or simple resolution (minor) |
|---|---|---|---|---|---|
| 20 | 67 | 1 | 6 | 11 | 2 |

Critical + major: **7 of 67 sentences (10%)**, on 7 of 20 bills. Compare local legislation in sample 01: 5% with
full text, 34% title only. State bills always have full text; the errors here are about **legal effect and
conditions**, not invented content.

## Findings

| # | Bill | Finding | Check | Severity |
|---|---|---|---|---|
| 6 | H.B. 683 (PAs and APRNs) | "allows these professionals to prescribe certain medications **on their own, rather than needing a supervising doctor**". The bill deletes the duty to **notify** the Department of Health of a delegation and to print the supervisor's name on a PA's prescription; supervision and delegation remain | C2 (legal effect) | **critical** |
| 2 | H.B. 673 (conservation easements) | "allows property owners to **request**" a release; the bill **requires** the district to release when the conditions are met | C2 (modality, understated) | major |
| 4 | H.B. 7019 (OGSR, Military Affairs) | "will remain exempt … **unless** the Legislature reenacts the exemption by October 2, 2031": inverted. The exemption **repeals** on that date unless reenacted | C2 | major |
| 8 | S.B. 1758 (public assistance) | Medicaid work requirements stated as a condition of coverage; the bill requires the agency to **seek federal approval** and **prohibits implementing** until conditions are met | C3 (dropped condition) | major |
| 12 | S.B. 1426 (officer personnel files) | Adds a purpose ("to track who is accessing") the bill does not state | C7 | major |
| 17 | S.B. 1188 (utility rates) | Same-rate rule stated without the bill's "under certain circumstances" | C3 | major |
| 18 | H.B. 143 (offenses evidencing prejudice) | "The goal is to reclassify crimes based on how they affect the victim": invented and wrong (the basis is prejudice toward the victim's political ideology) | C7, C2 | major |
| 10, 16 | S.J.R. 282, H.R. 761 | "This bill" for a joint resolution and a House resolution | C4 | minor |
| 1, 3, 5, 14, 15, 17, 19 | | Details beyond the title not located in the text read (U). S.B. 556 lists portfolio and employment options for students with disabilities as changes; they may be existing law | C1 | U |

## A second defect found while sampling: stale "Introduced" status

Three of the 20 (H.B. 7019, S.B. 1288, S.B. 556) show **"Introduced"** although the 2026 Regular Session ended
months ago. Their last action is "Laid on Table, refer to CS/…": they were replaced by a companion committee
substitute. Across the session, **352 bills** still show "Introduced". A reader sees them as alive. LegiScan keeps
status code 1 for these; the site's timeline already treats "Laid on Table" as a replacement, not an outcome, but
the status field does not. Tracked as defect D9 (`W1_BASELINE_2026-11-25.md`).

## Patterns and fixes

1. **Legal-effect errors on deletions.** H.B. 683 removes a notice requirement; the summary reads it as removing
   supervision. The prompt describes "[deleted: …]" markers, but the model generalises from what was deleted to
   what that implies. Fix to test: a rule that a deletion is described as removing exactly the deleted words'
   requirement, nothing broader; an automated check that flags "on their own", "no longer need" and similar
   phrases for review.
2. **Dropped conditions** (S.B. 1758, S.B. 1188): the same rule the local prompt now has ("keep every condition
   and limit") belongs in the state prompt.
3. **Sunset logic inverted** (H.B. 7019): Open Government Sunset Review bills follow one formula; a fixed
   explanation for that bill type would remove the risk.
4. **Invented purposes** (S.B. 1426, H.B. 143): the state prompt forbids speculating about "intent", but "goal"
   and "to track" slip through; add them to the guard words.

Changing the state prompt re-summarizes every state bill (about 5,800). Do it once, with all four fixes, after
the owner signs off, and re-audit this same sample (same seed) afterwards.
