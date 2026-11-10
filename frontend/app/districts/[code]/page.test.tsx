import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const getDistrict = vi.fn();
vi.mock("@/lib/server-api", () => ({ getDistrict: (...a: unknown[]) => getDistrict(...a) }));
const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});
vi.mock("next/navigation", () => ({ notFound: () => notFound() }));

import DistrictPage from "./page";

const detail = (over = {}) => ({
  code: "HD-101", chamber: "house", number: 101,
  map_plan: { key: "k", name: "Plan 2022", effective_from: "2022-11-08", effective_to: null },
  members: [
    { person_entity_id: "p1", name: "Pat Doe", party: "REP", start_date: "2022-11-22", end_date: null, end_reason: null, current: true, basis: "tenure" },
    { person_entity_id: "p2", name: "Lee Roe", party: null, start_date: null, end_date: null, end_reason: null, current: true, basis: "current_roster" },
  ],
  sponsored_bills: { total: 30, note: "Bills filed by members while they held this seat.", items: [{ entity_id: "b1", bill_number: "HB 7", name: "A bill", status: "Introduced", last_action_date: null }] },
  census_profile: {
    population: "residents", label: "Estimates for the people who live in this district. They describe residents, not voters or the electorate.",
    source: "ACS",
    profile: [{ badge_slug: "housing", badge_label: "Housing", vintage: "2024", metrics: [
      { label: "Renter households", unit: "households", estimate: 40000, margin_of_error: 1200, reliability: "ok", suppressed: false },
      { label: "Small group", unit: "people", estimate: 100, margin_of_error: 60, reliability: "high_moe", suppressed: false },
      { label: "Tiny group", unit: "people", estimate: null, margin_of_error: 150, reliability: "suppressed", suppressed: true },
    ] }],
  },
  ...over,
});

const renderPage = async (code = "HD-101") => render(await DistrictPage({ params: Promise.resolve({ code }) }));

describe("DistrictPage", () => {
  beforeEach(() => { getDistrict.mockReset(); notFound.mockClear(); });

  it("shows members, bills, the residents label, vintage and margins of error", async () => {
    getDistrict.mockResolvedValue(detail());
    await renderPage();
    expect(screen.getByRole("link", { name: "Pat Doe" })).toHaveAttribute("href", "/people/p1");
    expect(screen.getByText(/current roster; the seat's history is not on record/i)).toBeInTheDocument();
    expect(screen.getByText(/not voters or the electorate/)).toBeInTheDocument();
    expect(screen.getByText(/American Community Survey 5-year estimates, 2024/)).toBeInTheDocument();
    expect(screen.getByText(/±1,200 margin of error/)).toBeInTheDocument();
    expect(screen.getByText(/Low reliability/)).toBeInTheDocument();
    expect(screen.getByText(/Not shown: the margin of error is as large as the estimate/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See all 30 in the bill list" })).toHaveAttribute("href", "/?district=HD-101");
  });

  it("404s an unknown district and says so when the API is down", async () => {
    getDistrict.mockResolvedValue(undefined);
    await expect(renderPage("HD-999")).rejects.toThrow("NEXT_NOT_FOUND");
    getDistrict.mockResolvedValue(null);
    await renderPage();
    expect(screen.getByText(/couldn.t be loaded/)).toBeInTheDocument();
  });
});
