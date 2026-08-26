import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BrowsePage from "./page";
import * as api from "@/lib/api";
import type { BillListItem } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  fetchBills: vi.fn(),
  fetchElections: vi.fn(() => Promise.reject(new Error("not under test"))),
  fetchStatuses: vi.fn(() => Promise.resolve([])),
}));

vi.mock("@/components/BillCard", () => ({
  default: ({ bill }: { bill: BillListItem }) => <div>{bill.bill_number}</div>,
}));

let searchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams,
}));

function makeBill(bill_number: string): BillListItem {
  return {
    entity_id: bill_number,
    bill_number,
    name: `Title for ${bill_number}`,
    session: "2026 Regular Session",
    chamber: "House",
    status: "Introduced",
    jurisdiction_level: "state",
    jurisdiction_name: "FL",
    geo_scope_type: "statewide",
    geo_scope_names: ["FL"],
    introduced_date: null,
    last_action_date: null,
    what_it_does: null,
    source_count: 0,
    full_text_url: null,
    primary_sponsor: null,
  };
}

describe("BrowsePage", () => {
  beforeEach(() => {
    searchParams = new URLSearchParams();
    vi.mocked(api.fetchBills).mockReset();
  });

  it("shows an empty-state message when no bills match", async () => {
    vi.mocked(api.fetchBills).mockResolvedValueOnce({ total: 0, items: [] });
    render(<BrowsePage />);

    expect(await screen.findByText(/no bills match your filters/i)).toBeInTheDocument();
  });

  it("passes the geo filter from the URL through to the API and shows it in the heading", async () => {
    searchParams = new URLSearchParams({ geo: "Miami-Dade County" });
    vi.mocked(api.fetchBills).mockResolvedValueOnce({ total: 1, items: [makeBill("R-26-0001")] });

    render(<BrowsePage />);

    await waitFor(() =>
      expect(api.fetchBills).toHaveBeenCalledWith(
        expect.objectContaining({ geo_scope_name: "Miami-Dade County", offset: 0 }),
      ),
    );
    expect(await screen.findByText(/filtered to/i)).toBeInTheDocument();
    expect(screen.getByText("Miami-Dade County")).toBeInTheDocument();
  });

  it("shows pagination and advances to the next page on click", async () => {
    vi.mocked(api.fetchBills).mockResolvedValueOnce({ total: 120, items: [makeBill("HB 1")] });
    const user = userEvent.setup();
    render(<BrowsePage />);

    expect(await screen.findByText(/120 bills — page 1 of 3/i)).toBeInTheDocument();

    vi.mocked(api.fetchBills).mockResolvedValueOnce({ total: 120, items: [makeBill("HB 2")] });
    await user.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() =>
      expect(api.fetchBills).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 50 })),
    );
    expect(await screen.findByText(/120 bills — page 2 of 3/i)).toBeInTheDocument();
  });

  it("disables Previous on the first page", async () => {
    vi.mocked(api.fetchBills).mockResolvedValueOnce({ total: 120, items: [makeBill("HB 1")] });
    render(<BrowsePage />);

    await screen.findByText(/120 bills — page 1 of 3/i);
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
  });
});


describe("BrowsePage status filter", () => {
  beforeEach(() => {
    searchParams = new URLSearchParams();
    vi.mocked(api.fetchBills).mockReset();
    vi.mocked(api.fetchStatuses).mockReset();
  });

  it("offers statuses from the data with their counts", async () => {
    vi.mocked(api.fetchBills).mockResolvedValue({ total: 0, items: [] });
    vi.mocked(api.fetchStatuses).mockResolvedValue([
      { status: "Failed", count: 1280 },
      { status: "Introduced", count: 384 },
    ]);
    render(<BrowsePage />);

    // Options come from the data, not a hardcoded list -- the three sources
    // use different vocabularies and a fixed list would drift.
    expect(await screen.findByRole("option", { name: "Failed (1280)" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Introduced (384)" })).toBeInTheDocument();
  });

  it("passes the chosen status through to the API", async () => {
    vi.mocked(api.fetchBills).mockResolvedValue({ total: 0, items: [] });
    vi.mocked(api.fetchStatuses).mockResolvedValue([{ status: "Passed", count: 255 }]);
    const user = userEvent.setup();
    render(<BrowsePage />);

    await screen.findByRole("option", { name: "Passed (255)" });
    await user.selectOptions(screen.getByLabelText(/filter by status/i), "Passed");

    await waitFor(() =>
      expect(api.fetchBills).toHaveBeenLastCalledWith(expect.objectContaining({ status: "Passed" })),
    );
  });

  it("clears a status that doesn't exist in the newly-chosen jurisdiction", async () => {
    // Otherwise the filter silently matches nothing and the page looks empty
    // for no visible reason.
    vi.mocked(api.fetchBills).mockResolvedValue({ total: 0, items: [] });
    vi.mocked(api.fetchStatuses).mockResolvedValue([{ status: "Enacted", count: 89 }]);
    const user = userEvent.setup();
    render(<BrowsePage />);

    await screen.findByRole("option", { name: "Enacted (89)" });
    await user.selectOptions(screen.getByLabelText(/filter by status/i), "Enacted");
    await waitFor(() =>
      expect(api.fetchBills).toHaveBeenLastCalledWith(expect.objectContaining({ status: "Enacted" })),
    );

    vi.mocked(api.fetchStatuses).mockResolvedValue([{ status: "Introduced", count: 344 }]);
    await user.selectOptions(screen.getByLabelText(/filter by jurisdiction/i), "FL");

    await waitFor(() =>
      expect(api.fetchBills).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: undefined, jurisdiction_name: "FL" }),
      ),
    );
  });
});
