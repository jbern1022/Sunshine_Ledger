/** The status a reader sees, derived from the stored status and last action.
 *  Display only: the stored value (and filters on it) are unchanged.
 *
 *  - Florida bills "Laid on Table, refer to CS/HB 1219" were replaced by a
 *    companion committee substitute. LegiScan keeps them at "Introduced",
 *    which reads as still alive months after the session ended (D9 in
 *    docs/grant-ready/W1_BASELINE_2026-11-25.md).
 *  - Clerk workflow words ("Agenda Ready") are not reader words. */

const CLERK_LABELS: Record<string, string> = {
  "Agenda Ready": "On an upcoming agenda",
  "Consent Agenda": "On a consent agenda",
};

const REPLACED = /^Laid on Table,?\s+refer(?:\s+to)?\s+(.+)$/i;

export function displayStatus(status: string | null | undefined, lastAction?: string | null): string {
  const s = (status ?? "").trim();
  if ((s === "Introduced" || s === "Engrossed") && lastAction) {
    const m = REPLACED.exec(lastAction.trim());
    if (m) return `Replaced by ${m[1].replace(/^to\s+/i, "").trim()}`;
  }
  return CLERK_LABELS[s] ?? s;
}
