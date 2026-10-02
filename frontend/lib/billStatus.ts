/** How to introduce a bill's own effective-date clause, given its status.
 *  The date comes from the bill text, so a bill that died never took effect
 *  and a pending one only would if enacted. */
export function effectiveLabel(status: string | null | undefined): string {
  const s = (status ?? "").toLowerCase();
  if (["passed", "enacted", "adopted"].some((w) => s.startsWith(w))) return "Takes effect";
  if (["failed", "vetoed", "withdrawn"].some((w) => s.startsWith(w))) return "Would have taken effect";
  return "If enacted, takes effect";
}

type Effective = { when: string; has_exceptions: boolean } | null | undefined;

/** How "Who it affects" introduces each group, from the bill's current
 *  status and its own effective-date clause (Data Model v1, "Provision
 *  status and effective dates"): Would apply / Will apply beginning ... /
 *  Applies / Would have applied. Enactment alone doesn't mean a provision
 *  applies yet, and an unknown start stays explicit in `note`. */
export function applicability(
  status: string | null | undefined,
  effective: Effective,
  today: Date = new Date(),
): { verb: string; note: string | null } {
  const s = (status ?? "").toLowerCase();
  if (["failed", "vetoed", "withdrawn"].some((w) => s.startsWith(w))) {
    return { verb: "Would have applied to", note: null };
  }
  if (!["passed", "enacted", "adopted"].some((w) => s.startsWith(w))) {
    return { verb: "Would apply to", note: "if enacted" };
  }
  const varies = effective?.has_exceptions ? " Some sections have their own dates; check the cited section." : "";
  if (!effective) {
    return { verb: "Applies once in effect to", note: "The bill text doesn't state when it takes effect." };
  }
  const start = Date.parse(effective.when);
  if (Number.isNaN(start)) {
    // "upon becoming a law", "upon signature by the Council President": in
    // effect once enacted, which the status already says it is.
    if (/^upon\b/i.test(effective.when)) return { verb: "Applies to", note: varies.trim() || null };
    return { verb: "Applies once in effect to", note: `Takes effect ${effective.when}, per the bill text.${varies}` };
  }
  if (start > today.getTime()) {
    return { verb: `Will apply beginning ${effective.when} to`, note: varies.trim() || null };
  }
  return { verb: "Applies to", note: varies.trim() || null };
}

const PROVISION_DATE_LABEL: Record<string, string> = {
  retroactive: "Applies retroactively to",
  tax_roll: "First applies to",
  expires: "Expires",
  takes_effect: "Takes effect",
  deadline: "Deadline:",
};

/** "Expires July 1, 2030" for a dated provision. */
export function provisionDateLabel(kind: string, when: string): string {
  return `${PROVISION_DATE_LABEL[kind] ?? "Date:"} ${when}`;
}
