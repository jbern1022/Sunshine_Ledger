import { describe, it, expect } from "vitest";
import { changeLabel, correctionNote, forTarget } from "./accountability";
import type { CorrectionOut, DisputeOut, ResponseOut } from "./types";

function correction(overrides: Partial<CorrectionOut> = {}): CorrectionOut {
  return {
    id: "c1", bill_entity_id: "b1", object_type: "bill_layer", object_id: "v1",
    prior_version: 1, current_version: 2, prior_text: "Deposits are returned in 15 days.",
    current_text: "Deposits are returned in 30 days.", change_type: "correction", severity: "material",
    trigger: "challenge", explanation: "The bill says 30 days.", evidence_links: [], origin: "sunshine_ledger_ai",
    was_reviewed: false, methodology_version: null, decided_at: "2026-10-02T12:00:00Z",
    decided_by_label: "Sunshine Ledger editor", ...overrides,
  };
}

const dispute: DisputeOut = {
  flag_id: "f1", object_type: "bill_layer", object_id: "v2", category: "misleading", severity: "critical",
  disputed_since: "2026-10-01T00:00:00Z",
};

const response: ResponseOut = {
  id: "r1", bill_entity_id: "b1", object_type: "bill", object_id: null, responder_name: "Rep. Example",
  responder_role: null, text: "We disagree.", full_text_url: null, verified_via: "verified via the filing contact",
  received_at: "2026-10-02T00:00:00Z", superseded_by_id: null,
};

const bill = { disputes: [dispute], corrections: [correction(), correction({ id: "c2", object_type: "vote", object_id: "e9" })], responses: [response] };

describe("forTarget", () => {
  it("matches a block by any of its version ids", () => {
    const got = forTarget(bill, "bill_layer", ["v2", "v1"]);
    expect(got.corrections.map((c) => c.id)).toEqual(["c1"]);
    expect(got.disputes.map((d) => d.flag_id)).toEqual(["f1"]);
    expect(got.responses).toEqual([]);
  });

  it("treats bill and page_copy as the bill itself", () => {
    const got = forTarget({ ...bill, corrections: [correction({ id: "c3", object_type: "page_copy", object_id: null })] }, "bill", []);
    expect(got.corrections.map((c) => c.id)).toEqual(["c3"]);
    expect(got.responses.map((r) => r.id)).toEqual(["r1"]);
  });

  it("copes with a bill payload that predates the fields", () => {
    expect(forTarget({}, "vote", ["e9"])).toEqual({ disputes: [], corrections: [], responses: [] });
  });
});

describe("labels", () => {
  it("names each change type", () => {
    expect(changeLabel(correction())).toBe("Corrected Oct 2, 2026");
    expect(changeLabel(correction({ change_type: "retraction" }))).toBe("Retracted Oct 2, 2026");
    expect(changeLabel(correction({ change_type: "source_correction" }))).toBe("Source corrected Oct 2, 2026");
  });

  it("gives material changes the earlier-version note", () => {
    expect(correctionNote(correction())).toBe(
      "An earlier version said “Deposits are returned in 15 days.” Corrected because: The bill says 30 days.",
    );
  });

  it("never reads a source's own correction as a Sunshine Ledger error", () => {
    expect(correctionNote(correction({ change_type: "source_correction" }))).toBe(
      "The source corrected its own record. The bill says 30 days.",
    );
  });

  it("puts no headline note on minor fixes", () => {
    expect(correctionNote(correction({ severity: "minor" }))).toBeNull();
  });
});
