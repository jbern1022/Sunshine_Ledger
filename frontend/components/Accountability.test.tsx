import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { CorrectionsSection } from "./Accountability";
import BillLayers from "./BillLayers";
import type { BillDetail, BillLayers as Layers, CorrectionOut, LayerVersion, ResponseOut } from "@/lib/types";

function version(overrides: Partial<LayerVersion> = {}): LayerVersion {
  return {
    id: "v2", version: 2, evidence_state: "supported", review_status: "not_reviewed", reviewed_at: null,
    scope_note: "Bill text", generated_by: "llm:qwen2.5:14b", method_version: "x/1",
    created_at: "2026-10-02T00:00:00Z", superseded_at: null, sources: [],
    items: [{ text: "Deposits are returned in 30 days.", section_ref: "Section 1", quote: null, assumptions: [], affected_groups: [] }],
    ...overrides,
  };
}

const correction: CorrectionOut = {
  id: "c1", bill_entity_id: "b1", object_type: "bill_layer", object_id: "v1", prior_version: 1, current_version: 2,
  prior_text: "Deposits are returned in 15 days.", current_text: "Deposits are returned in 30 days.",
  change_type: "correction", severity: "material", trigger: "challenge", explanation: "The bill says 30 days.",
  evidence_links: [{ url: "https://www.flsenate.gov/x.pdf", role: "supporting", note: "Filed bill text" }],
  origin: "sunshine_ledger_ai", was_reviewed: false, methodology_version: "interpretation/sunshine_ledger_ai/6",
  decided_at: "2026-10-02T12:00:00Z", decided_by_label: "Sunshine Ledger editor",
};

const response: ResponseOut = {
  id: "r1", bill_entity_id: "b1", object_type: "bill", object_id: null, responder_name: "Rep. Example",
  responder_role: "sponsor", text: "This bill does not change deposits.", full_text_url: null,
  verified_via: "verified via the contact on the candidate's Division of Elections filing",
  received_at: "2026-10-02T00:00:00Z", superseded_by_id: null,
};

const layers: Layers = {
  bill_says: [], expected_effect: [],
  interpretation: [{ origin: "sunshine_ledger_ai", current: version(), earlier_versions: [version({ id: "v1", version: 1 })] }],
};

function bill(overrides: Partial<BillDetail> = {}): BillDetail {
  return { entity_id: "b1", layers, disputes: [], corrections: [], responses: [], ...overrides } as unknown as BillDetail;
}

describe("block labels", () => {
  it("labels the corrected block with the date and the earlier-version note", () => {
    render(<BillLayers billEntityId="b1" layers={layers} hasStaffAnalysis={false} fallbackSummary={null} accountability={bill({ corrections: [correction] })} />);
    const region = screen.getByRole("region", { name: /Interpretation/ });
    expect(within(region).getByRole("link", { name: "Corrected Oct 2, 2026" })).toHaveAttribute("href", "#correction-c1");
    expect(within(region).getByText(/An earlier version said “Deposits are returned in 15 days.” Corrected because/)).toBeInTheDocument();
  });

  it("keeps a disputed block visible, labelled", () => {
    const dispute = { flag_id: "f1", object_type: "bill_layer", object_id: "v2", category: "misleading", severity: "critical" as const, disputed_since: "2026-10-01T00:00:00Z" };
    render(<BillLayers billEntityId="b1" layers={layers} hasStaffAnalysis={false} fallbackSummary={null} accountability={bill({ disputes: [dispute] })} />);
    const region = screen.getByRole("region", { name: /Interpretation/ });
    expect(within(region).getByRole("link", { name: "Disputed — under review" })).toBeInTheDocument();
    expect(within(region).getAllByText("Deposits are returned in 30 days.")[0]).toBeVisible();
  });
});

describe("CorrectionsSection", () => {
  it("renders nothing for a bill with no history", () => {
    const { container } = render(<CorrectionsSection bill={bill()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("keeps the before and after, the evidence and who decided", () => {
    render(<CorrectionsSection bill={bill({ corrections: [correction] })} />);
    expect(screen.getByText("Deposits are returned in 15 days.").tagName).toBe("DEL");
    expect(screen.getByText("Deposits are returned in 30 days.").tagName).toBe("INS");
    expect(screen.getByText(/to the Interpretation block/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Filed bill text" })).toHaveAttribute("href", "https://www.flsenate.gov/x.pdf");
    expect(screen.getByText(/AI-generated, not reviewed by a person/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All corrections across the site" })).toHaveAttribute("href", "/corrections");
  });

  it("shows responses verbatim with how identity was checked, and keeps superseded ones", () => {
    const old = { ...response, id: "r0", text: "Earlier reply.", superseded_by_id: "r1" };
    render(<CorrectionsSection bill={bill({ responses: [old, response] })} />);
    expect(screen.getAllByText("Response from Rep. Example", { exact: false })).toHaveLength(2);
    expect(screen.getByText("This bill does not change deposits.")).toBeInTheDocument();
    expect(screen.getAllByText(/Division of Elections filing/).length).toBeGreaterThan(0);
    expect(screen.getByText(/1 earlier response, since replaced/)).toBeInTheDocument();
    expect(screen.getByText("Earlier reply.")).toBeInTheDocument();
  });
});

describe("AccountabilityNotes in the page header", () => {
  it("leaves bill-level responses to the corrections section", async () => {
    const { AccountabilityNotes } = await import("./Accountability");
    const { container } = render(
      <AccountabilityNotes items={{ disputes: [], corrections: [], responses: [response] }} withResponses={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
