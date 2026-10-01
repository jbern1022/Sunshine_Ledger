import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import AreaContext from "./AreaContext";
import type { DemographicOverlay } from "@/lib/types";

const housing: DemographicOverlay = {
  badge_slug: "housing", badge_label: "Housing", source: "acs", geography_type: "district", geography_id: "HD-118",
  as_of: "2024", metrics: [
    { label: "Renter-occupied", estimate: 21345, margin_of_error: 812, unit: "housing units" },
    { label: "Owner-occupied", estimate: null, margin_of_error: null, unit: "housing units" },
  ],
};
const jobs: DemographicOverlay = {
  badge_slug: "labor_employment", badge_label: "Labor & Employment", source: "bls", geography_type: "county",
  geography_id: "Duval", as_of: "Jul 2026",
  metrics: [{ label: "Unemployment rate", estimate: 5.0, margin_of_error: null, unit: "percent" }],
};

describe("AreaContext", () => {
  it("shows ACS estimates with their margins of error and says whose district it is", () => {
    render(<AreaContext overlays={[housing]} />);
    expect(screen.getByRole("heading", { name: "Area context" })).toBeInTheDocument();
    expect(screen.getByText(/HD-118, the primary sponsor's district/)).toBeInTheDocument();
    expect(screen.getByText(/cover only the primary sponsor's district/)).toBeInTheDocument();
    expect(screen.getByText("21,345 housing units")).toBeInTheDocument();
    expect(screen.getByText(/± 812 margin of error/)).toBeInTheDocument();
    expect(screen.getByText(/not available/)).toBeInTheDocument();
    expect(screen.getByText(/American Community Survey/)).toBeInTheDocument();
  });

  it("labels county figures and leaves out a margin BLS doesn't publish", () => {
    render(<AreaContext overlays={[jobs]} />);
    expect(screen.getByText(/Duval County/)).toBeInTheDocument();
    expect(screen.getByText("5%")).toBeInTheDocument();
    expect(screen.queryByText(/margin of error/)).toBeNull();
    expect(screen.queryByText(/primary sponsor's district/)).toBeNull();
  });

  it("renders nothing without overlays", () => {
    const { container } = render(<AreaContext overlays={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
