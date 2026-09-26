import { describe, it, expect } from "vitest";
import { formatChecked, nightlySummary, sourceForBill } from "./freshness";
import type { SourceStatus } from "./types";

const status = (key: string, overrides: Partial<SourceStatus> = {}): SourceStatus => ({
  key,
  label: key,
  jurisdiction: null,
  schedule: "Nightly",
  note: "",
  last_checked_at: "2026-09-26T08:00:00Z",
  stale: false,
  bill_count: null,
  bills_with_text: null,
  ...overrides,
});

describe("freshness helpers", () => {
  it("formats a check date in Florida time", () => {
    // 02:00 UTC on Sep 26 is still Sep 25 in Florida.
    expect(formatChecked("2026-09-26T02:00:00Z")).toBe("Sep 25");
    expect(formatChecked(null)).toBe("never");
  });

  it("maps a bill's source system to its source", () => {
    const statuses = [status("legiscan"), status("legistar_jaxcityc"), status("iqm2_miami")];
    expect(sourceForBill(statuses, "legistar")?.key).toBe("legistar_jaxcityc");
    expect(sourceForBill(statuses, "unknown")).toBeUndefined();
    expect(sourceForBill(null, "legiscan")).toBeUndefined();
  });

  it("summarizes nightly sources by their oldest check and ignores weekly ones", () => {
    const summary = nightlySummary([
      status("legiscan", { last_checked_at: "2026-09-26T08:00:00Z" }),
      status("iqm2_miami", { last_checked_at: "2026-09-25T08:00:00Z", stale: true }),
      status("gdelt", { schedule: "Weekly", last_checked_at: "2026-09-01T00:00:00Z", stale: true }),
    ]);
    expect(summary.lastChecked).toBe("2026-09-25T08:00:00Z");
    expect(summary.stale.map((s) => s.key)).toEqual(["iqm2_miami"]);
  });
});
