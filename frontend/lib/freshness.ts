import type { SourceStatus } from "./types";

/** Bill.source_system -> the /sources/status key of the job that ingests it. */
const SOURCE_KEY_BY_SYSTEM: Record<string, string> = {
  legiscan: "legiscan",
  legistar: "legistar_jaxcityc",
  iqm2: "iqm2_miami",
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
): SourceStatus | undefined {
  const key = sourceSystem ? SOURCE_KEY_BY_SYSTEM[sourceSystem] : undefined;
  return key ? statuses?.find((s) => s.key === key) : undefined;
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
