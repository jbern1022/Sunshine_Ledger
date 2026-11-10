import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import FloridaPlaces from "./FloridaPlaces";
import type { FloridaPlaces as Data } from "@/lib/types";

const base: Data = {
  label: "Automatically found in the bill text, not yet reviewed by a person.",
  not_covered: "Only places the text names are listed. An empty list does not mean Florida is unaffected.",
  text_version: { type: "Engrossed in House", date: "2026-06-01", source_url: "https://www.congress.gov/x.htm" },
  findings: [
    { kind: "municipality", name: "Tampa", counties: ["Hillsborough"], section: "SEC. 102. FLOOD MITIGATION.", quote: "$2,500,000 for the City of Tampa, Florida, for stormwater work." },
    { kind: "named_place", name: "MacDill Air Force Base", counties: [], section: null, quote: "a project at MacDill Air Force Base, Florida." },
  ],
};

describe("FloridaPlaces", () => {
  it("shows each place with its exact sentence, the label, the text version and what it does not cover", () => {
    render(<FloridaPlaces data={base} />);
    expect(screen.getByText(/Automatically found in the bill text, not yet reviewed/)).toBeInTheDocument();
    expect(screen.getByText("Tampa")).toBeInTheDocument();
    expect(screen.getByText(/In Hillsborough County/)).toBeInTheDocument();
    expect(screen.getByText("$2,500,000 for the City of Tampa, Florida, for stormwater work.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Printed text" })).toHaveAttribute("href", "https://www.congress.gov/x.htm");
    expect(screen.getByText(/does not mean Florida is unaffected/)).toBeInTheDocument();
  });

  it("says plainly when there is no text or no place, without implying no effect", () => {
    const { rerender } = render(<FloridaPlaces data={{ ...base, text_version: null, findings: [] }} />);
    expect(screen.getByText(/don't have the text of this bill yet/)).toBeInTheDocument();
    rerender(<FloridaPlaces data={{ ...base, findings: [] }} />);
    expect(screen.getByText(/No Florida place is named in the text we have/)).toBeInTheDocument();
    expect(screen.getByText(/does not mean Florida is unaffected/)).toBeInTheDocument();
  });
});
