/** How to introduce a bill's own effective-date clause, given its status.
 *  The date comes from the bill text, so a bill that died never took effect
 *  and a pending one only would if enacted. */
export function effectiveLabel(status: string | null | undefined): string {
  const s = (status ?? "").toLowerCase();
  if (["passed", "enacted", "adopted"].some((w) => s.startsWith(w))) return "Takes effect";
  if (["failed", "vetoed", "withdrawn"].some((w) => s.startsWith(w))) return "Would have taken effect";
  return "If enacted, takes effect";
}
