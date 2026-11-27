import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StaffAnalysisBox from "./StaffAnalysisBox";
import type { StaffAnalysisExcerpt } from "@/lib/types";

function excerpt(overrides: Partial<StaffAnalysisExcerpt> = {}): StaffAnalysisExcerpt {
  return {
    committee: "Housing, Agriculture & Tourism Subcommittee",
    analysis_date: "2026-06-29",
    source_url: "https://www.flsenate.gov/Session/Bill/2026/1389/Analyses/h1389z1.HAT.PDF",
    effect: "Live Local Act\n\nThe bill amends the Live Local Act (Act) and requires:\n\n• Local governments1 to authorize uses.",
    fiscal: "LOCAL GOVERNMENT:\n\nThe bill has an indeterminate impact on local governments.",
    truncated: false,
    analyses_count: 3,
    is_latest: true,
    ...overrides,
  };
}

describe("StaffAnalysisBox", () => {
  it("quotes the staff's words and names the analysis it came from", () => {
    render(<StaffAnalysisBox analysis={excerpt()} />);
    expect(screen.getByRole("heading", { name: "What legislative staff say this does" })).toBeInTheDocument();
    expect(screen.getByText(/Housing, Agriculture & Tourism Subcommittee, Jun 29, 2026/)).toBeInTheDocument();
    expect(screen.getByText("• Local governments1 to authorize uses.")).toBeInTheDocument();
    expect(screen.getByText("The bill has an indeterminate impact on local governments.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Read the staff analysis (PDF)" })).toHaveAttribute(
      "href", "https://www.flsenate.gov/Session/Bill/2026/1389/Analyses/h1389z1.HAT.PDF",
    );
    expect(screen.getByText(/Not written or summarized by Sunshine Ledger/)).toBeInTheDocument();
  });

  it("folds a long section after four paragraphs, without cutting anything", () => {
    const effect = Array.from({ length: 7 }, (_, i) => `Paragraph ${i + 1}.`).join("\n\n");
    render(<StaffAnalysisBox analysis={excerpt({ effect, fiscal: null })} />);
    expect(screen.getByText("Read 3 more paragraphs")).toBeInTheDocument();
    expect(screen.getByText("Paragraph 7.")).toBeInTheDocument();
  });

  it("says when an older analysis is shown and when the text was cut", () => {
    render(<StaffAnalysisBox analysis={excerpt({ is_latest: false, truncated: true })} />);
    expect(screen.getByText(/newest of the 3 staff analyses with these sections/)).toBeInTheDocument();
    expect(screen.getByText(/The rest is in the PDF/)).toBeInTheDocument();
  });
});
