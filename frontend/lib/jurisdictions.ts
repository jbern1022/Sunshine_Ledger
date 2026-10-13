import type { SourceStatus } from "./types";

/** Cities with local bills. The location proxy matches a visitor's city against
 *  this list, and the homepage filter falls back to it when /sources/status is
 *  unreachable. Keep in step with CLIENT_JURISDICTIONS (backend/app/pipeline/
 *  legistar.py) and the Miami iQM2 source; the homepage filter itself reads the
 *  live source list, so a city missing here still appears there. */
export const LOCAL_JURISDICTIONS = ["Miami", "Jacksonville", "Fort Lauderdale", "Coral Gables", "Key West", "Delray Beach"] as const;

export interface JurisdictionOption {
  label: string;
  value: string;
}

const BASE: JurisdictionOption[] = [
  { label: "All jurisdictions", value: "" },
  { label: "Florida (state)", value: "FL" },
];

/** Homepage jurisdiction dropdown: every city the site actually ingests (from
 *  /sources/status), in a stable alphabetical order. */
export function jurisdictionOptions(statuses: SourceStatus[] | null): JurisdictionOption[] {
  const cities = statuses
    ? Array.from(new Set(statuses.map((s) => s.jurisdiction).filter((j): j is string => !!j && j !== "FL")))
    : [...LOCAL_JURISDICTIONS];
  return [...BASE, ...cities.sort().map((c) => ({ label: c, value: c }))];
}
