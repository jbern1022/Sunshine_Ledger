import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import BillLayers from "./BillLayers";
import type { BillLayers as Layers, LayerVersion } from "@/lib/types";

function version(overrides: Partial<LayerVersion> = {}): LayerVersion {
  return {
    id: "v1", version: 1, evidence_state: "supported", review_status: "not_reviewed", reviewed_at: null,
    scope_note: "Bill text", generated_by: "llm:llama3.1:8b", method_version: "x/1",
    created_at: "2026-09-23T00:00:00Z", superseded_at: null, sources: [],
    items: [{ text: "Item text", section_ref: "Section 1", quote: null, assumptions: [], affected_groups: [] }],
    ...overrides,
  };
}

const empty: Layers = { bill_says: [], interpretation: [], expected_effect: [] };

function section(name: RegExp) {
  return screen.getByRole("region", { name });
}

describe("BillLayers", () => {
  it("renders each block only under its own layer heading", () => {
    const layers: Layers = {
      ...empty,
      interpretation: [{ origin: "sunshine_ledger_ai", current: version({ items: [{ text: "Interp only", section_ref: "Section 1", quote: null, assumptions: [], affected_groups: [] }] }), earlier_versions: [] }],
    };
    render(<BillLayers layers={layers} hasStaffAnalysis={false} fallbackSummary={null} />);
    expect(within(section(/Interpretation/)).getByText("Interp only")).toBeInTheDocument();
    expect(within(section(/Expected Effect/)).queryByText("Interp only")).toBeNull();
    expect(within(section(/Bill Says/)).queryByText("Interp only")).toBeNull();
  });

  it("shows the exact empty states", () => {
    render(<BillLayers layers={empty} hasStaffAnalysis={false} fallbackSummary={null} />);
    const interp = section(/Interpretation/);
    expect(within(interp).getByText("No staff analysis published.")).toBeInTheDocument();
    expect(within(interp).getByText("Not yet evaluated.")).toBeInTheDocument();
  });

  it("says not yet evaluated for a staff block when an analysis exists", () => {
    render(<BillLayers layers={empty} hasStaffAnalysis={true} fallbackSummary={null} />);
    expect(within(section(/Interpretation/)).getAllByText("Not yet evaluated.")).toHaveLength(2);
  });

  it("labels AI blocks by review status and Bill Says by quote checking", () => {
    const layers: Layers = {
      bill_says: [{ origin: "bill_text", current: version({ items: [{ text: "Quoted", section_ref: "Section 2", quote: "Quoted", assumptions: [], affected_groups: [] }] }), earlier_versions: [] }],
      interpretation: [
        { origin: "legislative_staff", current: version({ scope_note: "Staff analysis, Rules, 2026-03-01", review_status: "reviewed", reviewed_at: "2026-09-30T00:00:00Z" }), earlier_versions: [] },
        { origin: "sunshine_ledger_ai", current: version(), earlier_versions: [] },
      ],
      expected_effect: [],
    };
    render(<BillLayers layers={layers} hasStaffAnalysis={true} fallbackSummary={null} />);
    expect(within(section(/Bill Says/)).getByText("Quotes checked word for word against the bill text")).toBeInTheDocument();
    const interp = section(/Interpretation/);
    expect(within(interp).getByText(/Legislative staff analysis · Rules, 2026-03-01 · condensed by AI/)).toBeInTheDocument();
    expect(within(interp).getByText(/reviewed by a person on Sep 30, 2026/)).toBeInTheDocument();
    expect(within(interp).getByText(/Sunshine Ledger analysis · AI-generated/)).toBeInTheDocument();
    expect(within(interp).getByText(/not reviewed by a person/)).toBeInTheDocument();
  });

  it("shows insufficient evidence with its scope note", () => {
    const layers: Layers = {
      ...empty,
      expected_effect: [{ origin: "sunshine_ledger_ai", current: version({ evidence_state: "insufficient_evidence", items: [], scope_note: "No effects traceable to a specific bill section" }), earlier_versions: [] }],
    };
    render(<BillLayers layers={layers} hasStaffAnalysis={false} fallbackSummary={null} />);
    expect(within(section(/Expected Effect/)).getByText(/Insufficient evidence/)).toBeInTheDocument();
    expect(within(section(/Expected Effect/)).getByText(/No effects traceable to a specific bill section/)).toBeInTheDocument();
  });

  it("includes the Expected Effect disclaimer", () => {
    render(<BillLayers layers={empty} hasStaffAnalysis={false} fallbackSummary={null} />);
    expect(screen.getByText("What may happen. Forecasts, not established facts, and not legal or financial advice.")).toBeInTheDocument();
  });

  it("lists earlier versions", () => {
    const layers: Layers = {
      ...empty,
      interpretation: [{
        origin: "sunshine_ledger_ai",
        current: version({ version: 2 }),
        earlier_versions: [version({ id: "v0", version: 1, superseded_at: "2026-09-20T00:00:00Z", items: [{ text: "Older reading", section_ref: null, quote: null, assumptions: [], affected_groups: [] }] })],
      }],
    };
    render(<BillLayers layers={layers} hasStaffAnalysis={false} fallbackSummary={null} />);
    expect(screen.getByText("1 earlier version")).toBeInTheDocument();
    expect(screen.getByText("Older reading")).toBeInTheDocument();
  });

  it("links a staff block to the analysis PDF with its retrieval date", () => {
    const layers: Layers = {
      ...empty,
      interpretation: [{
        origin: "legislative_staff",
        current: version({
          scope_note: "Staff analysis, Rules, 2026-03-01",
          sources: [{ id: "s1", url: "https://flsenate.gov/a.pdf", publisher: "Florida Legislature staff", source_type: "fl_staff_analysis", retrieved_at: "2026-09-23T00:00:00Z" }],
        }),
        earlier_versions: [],
      }],
    };
    render(<BillLayers layers={layers} hasStaffAnalysis={true} fallbackSummary={null} />);
    expect(screen.getByRole("link", { name: "staff analysis (PDF)" })).toHaveAttribute("href", "https://flsenate.gov/a.pdf");
    expect(screen.getByText(/retrieved Sep 23, 2026/)).toBeInTheDocument();
  });

  it("falls back to the labeled summary when there is no Bill Says", () => {
    render(<BillLayers layers={empty} hasStaffAnalysis={false} fallbackSummary="Plain summary." />);
    const says = section(/Bill Says/);
    expect(within(says).getByText("AI summary of the official description")).toBeInTheDocument();
    expect(within(says).getByText("Plain summary.")).toBeInTheDocument();
  });
});
