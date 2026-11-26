# Broward County: how county items read (2026-11-25)

Todoist `6hm2FqVh66Mmww6G`. Read from the public API, newest 8 Broward County items. Not a random sample;
an editorial read of what a reader sees today.

## What works

* Kinds are right: motions stay `other`; the one budget resolution is `legislation`. The verb-anchored title rule
  is doing its job.
* Scope reads "county — Broward County" on every item.
* Most descriptions name the record type and the request ("This item is a motion to amend … meeting calendar").

## What reads wrong

| Item | Description says | Problem | Fix |
|---|---|---|---|
| 26-1619 (reappointment) | "This request asks the **Broward Regional Health Planning Council** to reappoint Barbara S. Effman" | Wrong actor: the **County Commission** reappoints her **to** the council | Name the acting board in the item prompt ("The board acting is the Broward County Board of County Commissioners"), as the local-legislation prompt now does |
| 26-1618 (LETF budget resolution) | "This bill transfers funds …" | "bill" for a county resolution | Fixed on `fix/local-legislation-summaries` (not deployed) |
| 26-1607 (new Health Care Administration Office) | "a proposed resolution, which is a type of motion" | Muddled: it is a motion to waive a Code section and adopt a resolution | Same prompt change; the title's two verbs ("WAIVE … ADOPT") should both be named |
| 26-1623 (library naming) | "This item is a Resolution …" | The record is a motion (to waive a naming rule, then adopt the naming resolution) | Same |
| 26-1627 (TEFRA hearing) | Names the Michigan Finance Authority and $1.4 billion | Not checked against the item text (U); TEFRA hearings for out-of-state conduit issuers are real, but verify before featuring | — |
| all | Status "Agenda Ready" | Clerk's workflow word, not a reader's: it means "on an upcoming agenda" | Display map: "Agenda Ready" → "On an upcoming agenda" (no data change) |

## Recommendation

1. Extend the jurisdiction-and-actor rule from the local-legislation prompt to the non-legislation item prompt
   (scoped version bump `item2`; re-summarizes local non-legislation only). Owner sign-off needed: it is a
   re-summarize.
2. A display-label map for clerk statuses ("Agenda Ready", "Consent Agenda", "Draft") in the frontend. No data
   change, no re-summarize. Engineering-only.
3. Then apply the same read to the other eight county Legistar clients before closing the ticket.
