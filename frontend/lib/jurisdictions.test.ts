import { describe, it, expect } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { jurisdictionOptions, localJurisdictions, LOCAL_JURISDICTIONS } from "./jurisdictions";
import type { SourceStatus } from "./types";

const status = (key: string, jurisdiction: string | null): SourceStatus => ({
  key, label: key, jurisdiction, schedule: "Nightly", note: "", last_checked_at: null, stale: false,
  bill_count: null, bills_with_text: null,
});

describe("jurisdictionOptions", () => {
  it("lists each ingested city once, alphabetically, after All and Florida", () => {
    const opts = jurisdictionOptions([
      status("legiscan", "FL"),
      status("legistar_jaxcityc", "Jacksonville"),
      status("legistar_fortlauderdale", "Fort Lauderdale"),
      status("iqm2_miami", "Miami"),
      status("gdelt", null),
    ]);
    expect(opts.map((o) => o.value)).toEqual(["", "FL", "Fort Lauderdale", "Jacksonville", "Miami"]);
  });

  it("falls back to the known cities when the status list is unavailable", () => {
    expect(jurisdictionOptions(null).map((o) => o.value)).toEqual(["", "FL", ...[...LOCAL_JURISDICTIONS].sort()]);
  });
});

describe("localJurisdictions", () => {
  it("uses the live source list, so a newly enabled city needs no code change", () => {
    expect(localJurisdictions([status("legiscan", "FL"), status("legistar_newcity", "Newcity"), status("gdelt", null)])).toEqual([
      "Newcity",
    ]);
  });

  it("falls back to the built-in list, sorted, when the source list is unavailable", () => {
    expect(localJurisdictions(null)).toEqual([...LOCAL_JURISDICTIONS].sort());
  });
});

describe("the fallback list stays in step with the backend registry", () => {
  const registry = resolve(__dirname, "../../backend/app/pipeline/legistar.py");

  // CI checks out the whole repo; a frontend-only checkout has nothing to compare.
  it.skipIf(!existsSync(registry))("names every city registered in CLIENT_JURISDICTIONS, and nothing else", () => {
    const src = readFileSync(registry, "utf8");
    const registered = new Set([...src.matchAll(/"jurisdiction":\s*"([^"]+)"/g)].map((m) => m[1]));
    expect(registered.size).toBeGreaterThan(10); // the pattern still finds the registry
    expect([...LOCAL_JURISDICTIONS].sort()).toEqual([...registered].sort());
  });
});
