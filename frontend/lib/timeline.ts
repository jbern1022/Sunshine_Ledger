import type { ActionOut, AmendmentOut, RollCallOut } from "./types";

/** One row of the "How it became law" timeline. */
export interface TimelineStep {
  date: string; // YYYY-MM-DD
  chamber: string | null;
  kind: "filed" | "action" | "amendment" | "vote" | "outcome";
  text: string;
  detail?: string;
  href?: string; // in-page anchor to the vote or amendment
  key: boolean; // shown in the default "key steps" view
}

// Wording from the Florida history entries (2026 Regular Session, checked
// 2026-09-26). Two look final but aren't, so they stay ordinary steps:
// "Withdrawn from Rules" only changes a referral, and "Laid on Table under
// Rule 7.18(a)" / "Laid on Table, refer to CS/..." is the House procedure
// for replacing a bill with its committee substitute, which carries on.
const FILED = /^(Filed|Prefiled)\b/i;
const OUTCOME =
  /^(Approved by Governor|Vetoed|Became Law|Chapter No\.|Signed by Officers and presented to Governor|Died in )/i;
const ENACTED = /^(Approved by Governor|Became Law|Chapter No\.)/i;

const CHAMBER_CODES: Record<string, string> = { H: "House", S: "Senate" };

// Within one day: filed, then the day's other history, then amendments and
// votes, then outcomes -- e.g. an amendment adopted before the vote on the
// amended bill.
const DAY_ORDER: Record<TimelineStep["kind"], number> = { filed: 0, action: 1, amendment: 2, vote: 3, outcome: 4 };

function tally(v: RollCallOut): string {
  const counts = v.yea !== null && v.nay !== null ? ` ${v.yea}–${v.nay}` : "";
  return `${v.passed ? "passed" : "failed"}${counts}`;
}

export function buildTimeline(
  actions: ActionOut[],
  votes: RollCallOut[],
  amendments: AmendmentOut[],
): TimelineStep[] {
  let filedSeen = false;
  const steps: TimelineStep[] = actions.map((a) => {
    const kind = !filedSeen && FILED.test(a.action) ? "filed" : OUTCOME.test(a.action) ? "outcome" : "action";
    if (kind === "filed") filedSeen = true;
    return { date: a.date, chamber: a.chamber, kind, text: a.action, key: kind !== "action" };
  });
  for (const v of votes) {
    steps.push({
      date: v.date,
      chamber: v.chamber ? (CHAMBER_CODES[v.chamber] ?? v.chamber) : null,
      kind: "vote",
      text: v.description,
      detail: tally(v),
      href: `#roll-call-${v.roll_call_id}`,
      key: true,
    });
  }
  for (const a of amendments.filter((a) => a.adopted)) {
    steps.push({
      date: a.date,
      chamber: a.chamber,
      kind: "amendment",
      text: a.description ?? "Amendment",
      detail: "adopted",
      href: `#amendment-${a.id}`,
      key: true,
    });
  }
  // Stable sort: history entries keep their official order within a kind.
  return steps
    .map((step, i) => ({ step, i }))
    .sort(
      (x, y) =>
        x.step.date.localeCompare(y.step.date) ||
        DAY_ORDER[x.step.kind] - DAY_ORDER[y.step.kind] ||
        x.i - y.i,
    )
    .map(({ step }) => step);
}

/** Whether the history shows the bill becoming law, for the section title. */
export function becameLaw(actions: ActionOut[]): boolean {
  return actions.some((a) => ENACTED.test(a.action));
}

/** "Jan 9" -- dates are calendar days, so format them without a time zone shift. */
export function formatStepDate(date: string): string {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}
