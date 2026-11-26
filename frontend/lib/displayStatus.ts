/** The status a reader sees, derived from the stored status and last action.
 *  Display only: the stored value (and filters on it) are unchanged.
 *
 *  LegiScan leaves many Florida bills at "Introduced" (or "Engrossed") after
 *  their final action: on 2026-11-25, 352 bills of the ended 2026 Regular
 *  Session, 381 of 2025 and 449 of 2024 (D9 in
 *  docs/grant-ready/W1_BASELINE_2026-11-25.md). Their last action says what
 *  actually happened, so the label is read from it. Clerk workflow words
 *  ("Agenda Ready") are put into reader words. */

const CLERK_LABELS: Record<string, string> = {
  "Agenda Ready": "On an upcoming agenda",
  "Consent Agenda": "On a consent agenda",
};

// Final actions, most specific first. Counts are the 2026 Regular Session.
const FINAL_ACTIONS: [RegExp, (m: RegExpExecArray) => string][] = [
  // 201: replaced by a companion committee substitute
  [/^Laid on Table,?\s+refer(?:\s+to)?\s+(.+)$/i, (m) => `Replaced by ${m[1].trim()}`],
  // 5: "Adopted, companion bill(s) passed, see HR 8087 (Adopted)"
  [/^Adopted,\s+companion bill\(s\) passed,\s+see\s+(.+?)\s*(?:\(Adopted\))?$/i, (m) => `Replaced by ${m[1].trim()} (adopted)`],
  // 64: resolutions adopted without a vote
  [/^Adopted by Publication/i, () => "Adopted"],
  // 38: "Died on Calendar", "Died on Second Reading Calendar", "Died in …"
  [/^Died\b/i, () => "Died"],
  // 37: "Withdrawn prior to introduction", "Withdrawn from further consideration"
  [/^Withdrawn\b/i, () => "Withdrawn"],
  // 2: tabled with no companion named
  [/^Laid on Table\.?$/i, () => "Tabled"],
];

export function displayStatus(status: string | null | undefined, lastAction?: string | null): string {
  const s = (status ?? "").trim();
  if ((s === "Introduced" || s === "Engrossed") && lastAction) {
    const action = lastAction.trim();
    for (const [pattern, label] of FINAL_ACTIONS) {
      const m = pattern.exec(action);
      if (m) return label(m);
    }
  }
  return CLERK_LABELS[s] ?? s;
}
