import type { SourceStatus } from "./types";

/** Fallback list of places with local bills, used only when /sources/status is
 *  unreachable (the homepage filter and the IP-location default both read the
 *  live source list first, so a newly enabled city appears without a code
 *  change). Keep in step with CLIENT_JURISDICTIONS (backend/app/pipeline/
 *  legistar.py) and the Miami iQM2 source. */
export const LOCAL_JURISDICTIONS = [
  "Miami", "Jacksonville", "Broward County", "Fort Lauderdale", "Coral Gables", "Key West", "Delray Beach",
  "Hollywood", "Clearwater", "Miramar", "Doral", "Hallandale Beach", "Coconut Creek", "Pinecrest", "Margate",
  "Deltona", "Edgewater", "North Port", "Venice", "Plant City", "Wellington", "Marco Island", "Pinellas Park",
  "Hernando County", "DeSoto County", "Pinellas County", "Brevard County", "Marion County", "Martin County",
  "Polk County", "Seminole County", "Orange County",
] as const;

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
  return [...BASE, ...localJurisdictions(statuses).map((c) => ({ label: c, value: c }))];
}

/** Every local jurisdiction the site ingests, alphabetical: from the live
 *  source list when available, else the fallback list. */
export function localJurisdictions(statuses: SourceStatus[] | null): string[] {
  const names = statuses
    ? statuses.map((s) => s.jurisdiction).filter((j): j is string => !!j && j !== "FL")
    : [...LOCAL_JURISDICTIONS];
  return Array.from(new Set(names)).sort();
}
