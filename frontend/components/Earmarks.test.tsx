import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Earmarks from "./Earmarks";
import type { EarmarkList } from "@/lib/types";

const item = (over = {}) => ({
  id: "1", fiscal_year: 2027, stage: "requested" as const, stage_label: "A member's request. Not funding: it may never be included in a bill.",
  district: "CD-012", person_id: "p1", member: "Gus Bilirakis", party: "R", subcommittee: "Agriculture",
  recipient: "School Board of Pasco County", description: "Sustainable Futures Program", recipient_address: null, amount: 5000000,
  member_url: null, source_url: "https://appropriations.house.gov/x.xlsx", ...over,
});
const data = (over: Partial<EarmarkList> = {}): EarmarkList => ({ note: "From the House Appropriations Committee.", total: 1, items: [item()], ...over });

describe("Earmarks", () => {
  it("labels a request as a request and never as funding", () => {
    render(<Earmarks data={data()} district="CD-012" />);
    expect(screen.getByText("Requested")).toBeInTheDocument();
    expect(screen.getByText(/Not funding: it may never be included/)).toBeInTheDocument();
    expect(screen.getByText(/\$5,000,000/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Committee table" })).toHaveAttribute("href", "https://appropriations.house.gov/x.xlsx");
  });

  it("shows nothing when there are no rows, and says when it shows only some", () => {
    const { container } = render(<Earmarks data={data({ total: 0, items: [] })} district="CD-012" />);
    expect(container).toBeEmptyDOMElement();
    render(<Earmarks data={data({ total: 30 })} district="CD-012" />);
    expect(screen.getByText("Showing 1 of 30 for CD-012.")).toBeInTheDocument();
  });

  it("omits the amount when the source has none", () => {
    render(<Earmarks data={data({ items: [item({ amount: null })] })} district="CD-012" />);
    expect(screen.queryByText(/\$/)).toBeNull();
  });
});
