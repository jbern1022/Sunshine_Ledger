import type { SourceStatus } from "./types";

/** Bill.source_system -> the prefix of the /sources/status keys of the jobs that
 *  ingest it. Several cities can share one system (Legistar), so the bill's
 *  jurisdiction picks among them. */
const SOURCE_KEY_PREFIX_BY_SYSTEM: Record<string, string> = {
  legiscan: "legiscan",
  legistar: "legistar_",
  iqm2: "iqm2_",
};

/** "Sep 26", in Florida time. "never" if the source has no recorded check. */
export function formatChecked(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "America/New_York",
  });
}

export function sourceForBill(
  statuses: SourceStatus[] | null,
  sourceSystem: string | null | undefined,
  jurisdictionName?: string | null,
): SourceStatus | undefined {
  const prefix = sourceSystem ? SOURCE_KEY_PREFIX_BY_SYSTEM[sourceSystem] : undefined;
  if (!prefix || !statuses) return undefined;
  const candidates = statuses.filter((s) => s.key.startsWith(prefix));
  if (candidates.length <= 1) return candidates[0];
  // Never guess between cities: showing another city's check date would
  // claim freshness the bill's own source may not have.
  return candidates.find((s) => s.jurisdiction === jurisdictionName);
}

/** The bill sources that update nightly: the oldest of their last checks
 *  (so the note never claims more freshness than the laggiest source has),
 *  and which of them are stale. */
export function nightlySummary(statuses: SourceStatus[]): { lastChecked: string | null; stale: SourceStatus[] } {
  const nightly = statuses.filter((s) => s.schedule === "Nightly");
  const checks = nightly.map((s) => s.last_checked_at);
  const lastChecked = checks.includes(null) ? null : checks.sort()[0] ?? null;
  return { lastChecked, stale: nightly.filter((s) => s.stale) };
}
