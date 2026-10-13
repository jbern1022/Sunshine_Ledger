import { describe, it, expect } from "vitest";
import { jurisdictionOptions, LOCAL_JURISDICTIONS } from "./jurisdictions";
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
