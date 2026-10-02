import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import WhoItAffects from "./WhoItAffects";
import type { LayerBlock, LayerVersion } from "@/lib/types";

function block(overrides: Partial<LayerVersion> = {}): LayerBlock {
  return {
    origin: "sunshine_ledger_ai",
    earlier_versions: [],
    current: {
      id: "w1", version: 1, evidence_state: "supported", review_status: "not_reviewed", reviewed_at: null,
      scope_note: "Bill text", generated_by: "llm:qwen2.5:14b", method_version: "who_it_affects/sunshine_ledger_ai/1",
      created_at: "2026-10-01T00:00:00Z", superseded_at: null, sources: [],
      items: [
        {
          text: "Must return a tenant's deposit within 15 days.", group: "Landlords", change_kind: "obligation",
          quote: "A landlord shall return a tenant's security deposit within 15 days.", section_ref: "Section 1",
          conditions: [],
          exceptions: [{ text: "Owners of fewer than three units", quote: "This section does not apply to a landlord who owns fewer than three dwelling units." }],
          assumptions: [], affected_groups: ["Landlords"],
        },
        {
          text: "May apply for a rent assistance grant.", group: "Landlords", change_kind: "eligibility",
          quote: "A landlord may apply for a grant.", section_ref: "Section 2",
          conditions: [{ text: "Large counties only", quote: "available only in a county with a population of more than 1 million" }],
          exceptions: [], assumptions: [], affected_groups: ["Landlords"],
        },
      ],
      ...overrides,
    },
  };
}

describe("WhoItAffects", () => {
  it("words a pending bill conditionally and shows who, what, why, conditions and exceptions", () => {
    render(<WhoItAffects billEntityId="b1" block={block()} status="Introduced" effective={{ when: "July 1, 2027", has_exceptions: false }} />);
    expect(screen.getByRole("heading", { name: "Who it affects" })).toBeInTheDocument();
    expect(screen.getAllByText(/Would apply to/)).toHaveLength(2);
    expect(screen.getByText("Only if the bill is enacted.")).toBeInTheDocument();
    expect(screen.getByText(/Must return a tenant's deposit/)).toBeInTheDocument();
    expect(screen.getByText("Obligation")).toBeInTheDocument();
    expect(screen.getByText("Eligibility")).toBeInTheDocument();
    expect(screen.getByText(/Section 1/)).toBeInTheDocument();
    expect(screen.getByText(/Exception stated in the bill: Owners of fewer than three units/)).toBeInTheDocument();
    expect(screen.getByText(/Condition: Large counties only/)).toBeInTheDocument();
    expect(screen.getByText("not reviewed by a person", { exact: false })).toBeInTheDocument();
  });

  it("shows an exception once when its text just repeats the bill's sentence", () => {
    const b = block();
    b.current.items[0].exceptions = [{ text: "(a) Law enforcement agencies.", quote: "(a) Law enforcement agencies." }];
    render(<WhoItAffects billEntityId="b1" block={b} status="Introduced" effective={null} />);
    expect(screen.getAllByText(/Law enforcement agencies/)).toHaveLength(1);
  });

  it("uses the bill's fate for the verb", () => {
    render(<WhoItAffects billEntityId="b1" block={block()} status="Vetoed" effective={{ when: "July 1, 2027", has_exceptions: false }} />);
    expect(screen.getAllByText(/Would have applied to/)).toHaveLength(2);
  });

  it("shows insufficient evidence honestly", () => {
    render(
      <WhoItAffects
        billEntityId="b1"
        block={block({ evidence_state: "insufficient_evidence", items: [], scope_note: "No group the bill directly applies to could be tied to its text" })}
        status="Introduced"
        effective={null}
      />,
    );
    expect(screen.getByText(/No group the bill directly applies to/)).toBeInTheDocument();
    expect(screen.queryByText(/Would apply to/)).toBeNull();
  });
});
