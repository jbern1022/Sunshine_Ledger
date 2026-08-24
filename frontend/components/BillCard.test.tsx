import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BillCard from "./BillCard";
import type { BillListItem, BillDetail } from "@/lib/types";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({
  fetchBill: vi.fn(),
  submitFlag: vi.fn(),
}));

const baseBill: BillListItem = {
  entity_id: "bill-1",
  bill_number: "HB 123",
  name: "Test Bill Title",
  session: "2026 Regular Session",
  chamber: "House",
  status: "In Committee",
  jurisdiction_level: "state",
  jurisdiction_name: "FL",
  geo_scope_type: "statewide",
  geo_scope_names: ["FL"],
  introduced_date: "2026-01-01",
  last_action_date: "2026-02-01",
  what_it_does: "This bill does a thing.",
  source_count: 2,
  full_text_url: "https://example.com/bill",
  primary_sponsor: "Jane Smith",
};

const baseDetail: BillDetail = {
  ...baseBill,
  last_action: "Referred to committee",
  sponsors: [{ entity_id: "p1", name: "Jane Smith", relationship_type: "sponsor" }],
  claims: [
    {
      id: "c1",
      claim_type: "who_it_affects",
      claim_text: "Residents of Example County.",
      generated_by: "llm:llama3.1",
      source_count: 1,
      sources: [
        {
          id: "s1",
          url: "https://example.com/source",
          publisher: "Example Times",
          source_type: "legiscan_bill",
          retrieved_at: "2026-02-01T00:00:00Z",
        },
      ],
    },
  ],
  news: [],
};

describe("BillCard", () => {
  beforeEach(() => {
    vi.mocked(api.fetchBill).mockReset();
    vi.mocked(api.submitFlag).mockReset();
  });

  it("renders core bill info", () => {
    render(<BillCard bill={baseBill} />);
    expect(screen.getByRole("heading", { name: "HB 123" })).toBeInTheDocument();
    expect(screen.getByText("This bill does a thing.")).toBeInTheDocument();
    expect(screen.getByText("In Committee")).toBeInTheDocument();
    expect(screen.getByText("Sponsored by Jane Smith")).toBeInTheDocument();
  });

  it("expands to show sources after fetching bill detail", async () => {
    vi.mocked(api.fetchBill).mockResolvedValueOnce(baseDetail);
    const user = userEvent.setup();
    render(<BillCard bill={baseBill} />);

    await user.click(screen.getByRole("button", { name: /sources \(2\)/i }));

    await waitFor(() => expect(api.fetchBill).toHaveBeenCalledWith("bill-1"));
    expect(await screen.findByText(/Residents of Example County\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hide sources/i })).toBeInTheDocument();
  });

  it("submits a flag report", async () => {
    vi.mocked(api.submitFlag).mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    render(<BillCard bill={baseBill} />);

    await user.click(screen.getByRole("button", { name: /flag this/i }));
    await user.type(screen.getByLabelText(/what looks wrong/i), "The summary is inaccurate");
    await user.click(screen.getByRole("button", { name: /submit report/i }));

    await waitFor(() =>
      expect(api.submitFlag).toHaveBeenCalledWith({
        bill_entity_id: "bill-1",
        reason_text: "The summary is inaccurate",
        reporter_email: null,
      }),
    );
    expect(await screen.findByText(/sent for manual review/i)).toBeInTheDocument();
  });

  it("shows an error state if flag submission fails", async () => {
    vi.mocked(api.submitFlag).mockRejectedValueOnce(new Error("network error"));
    const user = userEvent.setup();
    render(<BillCard bill={baseBill} />);

    await user.click(screen.getByRole("button", { name: /flag this/i }));
    await user.type(screen.getByLabelText(/what looks wrong/i), "Something is wrong here");
    await user.click(screen.getByRole("button", { name: /submit report/i }));

    expect(await screen.findByText(/couldn.t submit/i)).toBeInTheDocument();
  });
});

describe("BillCard AI disclosure", () => {
  beforeEach(() => {
    vi.mocked(api.fetchBill).mockReset();
  });

  it("discloses AI authorship and names the model when sources are expanded", async () => {
    vi.mocked(api.fetchBill).mockResolvedValueOnce(baseDetail);
    const user = userEvent.setup();
    render(<BillCard bill={baseBill} />);

    await user.click(screen.getByRole("button", { name: /sources \(2\)/i }));

    // The privacy page says summaries are AI-generated, but nobody reading a
    // bill card sees that. This disclosure is the one at the point of use.
    expect(await screen.findByText(/written by an AI model/i)).toBeInTheDocument();
    expect(screen.getByText(/llama3\.1/)).toBeInTheDocument();
    expect(screen.getByText(/without a human reviewing each one/i)).toBeInTheDocument();
  });

  it("does not claim AI authorship when no LLM-generated claims exist", async () => {
    vi.mocked(api.fetchBill).mockResolvedValueOnce({
      ...baseDetail,
      claims: [{ ...baseDetail.claims[0], generated_by: "manual_review" }],
    });
    const user = userEvent.setup();
    render(<BillCard bill={baseBill} />);

    await user.click(screen.getByRole("button", { name: /sources \(2\)/i }));
    await screen.findByText(/Residents of Example County/);

    expect(screen.queryByText(/written by an AI model/i)).not.toBeInTheDocument();
  });
});
