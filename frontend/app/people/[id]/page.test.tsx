import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import PersonPage, { generateMetadata } from "./page";
import * as serverApi from "@/lib/server-api";
import type { PersonDetail } from "@/lib/types";

vi.mock("@/lib/server-api", () => ({
  getPerson: vi.fn(),
}));

const { notFoundMock } = vi.hoisted(() => ({
  notFoundMock: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));
vi.mock("next/navigation", () => ({
  notFound: notFoundMock,
}));

async function renderPersonPage(id = "p1") {
  const element = await PersonPage({ params: Promise.resolve({ id }) });
  render(element);
}

const basePerson: PersonDetail = {
  entity_id: "p1",
  name: "Jane Smith",
  district: "District 10",
  role: "Representative",
  party: "N/A",
  jurisdiction_name: "FL",
  sponsored_count: 2,
  bills: [],
};

describe("PersonPage", () => {
  beforeEach(() => {
    vi.mocked(serverApi.getPerson).mockReset();
    notFoundMock.mockClear();
  });

  it("calls notFound() when the sponsor doesn't exist", async () => {
    vi.mocked(serverApi.getPerson).mockResolvedValueOnce(null);
    await expect(renderPersonPage("missing")).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFoundMock).toHaveBeenCalled();
  });

  it("renders the header fields joined in order and the no-rating disclaimer", async () => {
    vi.mocked(serverApi.getPerson).mockResolvedValueOnce(basePerson);
    await renderPersonPage();

    expect(screen.getByRole("heading", { name: "Jane Smith" })).toBeInTheDocument();
    expect(screen.getByText("Representative · District 10 · N/A · FL")).toBeInTheDocument();
    expect(screen.getByText(/not a voting record/i)).toBeInTheDocument();
  });

  it("shows an empty-state message when there are no tracked bills", async () => {
    vi.mocked(serverApi.getPerson).mockResolvedValueOnce({ ...basePerson, bills: [] });
    await renderPersonPage();
    expect(screen.getByText(/no tracked bills for this sponsor/i)).toBeInTheDocument();
  });

  it("distinguishes co-sponsored bills from sponsored ones", async () => {
    vi.mocked(serverApi.getPerson).mockResolvedValueOnce({
      ...basePerson,
      bills: [
        { entity_id: "b1", bill_number: "HB 1", name: "x", status: "Introduced", relationship_type: "sponsor", last_action_date: null, what_it_does: null },
        { entity_id: "b2", bill_number: "HB 2", name: "y", status: "Introduced", relationship_type: "co_sponsor", last_action_date: null, what_it_does: null },
      ],
    });
    await renderPersonPage();

    expect(screen.getByText("sponsor")).toBeInTheDocument();
    expect(screen.getByText("co-sponsor")).toBeInTheDocument();
  });

  it("falls back to a placeholder when a bill has no generated summary yet", async () => {
    vi.mocked(serverApi.getPerson).mockResolvedValueOnce({
      ...basePerson,
      bills: [
        { entity_id: "b1", bill_number: "HB 1", name: "x", status: "Introduced", relationship_type: "sponsor", last_action_date: "2026-02-01", what_it_does: null },
      ],
    });
    await renderPersonPage();

    expect(screen.getByText(/no summary generated yet/i)).toBeInTheDocument();
    expect(screen.getByText(/last action 2026-02-01/)).toBeInTheDocument();
  });
});

describe("PersonPage generateMetadata", () => {
  beforeEach(() => {
    vi.mocked(serverApi.getPerson).mockReset();
  });

  it("falls back to a not-found title when the sponsor doesn't exist", async () => {
    vi.mocked(serverApi.getPerson).mockResolvedValueOnce(null);
    const metadata = await generateMetadata({ params: Promise.resolve({ id: "missing" }) });
    expect(metadata.title).toBe("Sponsor not found — Sunshine Ledger");
  });

  it("includes role/district qualifiers in the title when present", async () => {
    vi.mocked(serverApi.getPerson).mockResolvedValueOnce(basePerson);
    const metadata = await generateMetadata({ params: Promise.resolve({ id: "p1" }) });
    expect(metadata.title).toBe("Jane Smith (Representative District 10) | Sunshine Ledger");
  });

  it("omits the parenthetical qualifier entirely when role and district are both absent", async () => {
    vi.mocked(serverApi.getPerson).mockResolvedValueOnce({ ...basePerson, role: null, district: null });
    const metadata = await generateMetadata({ params: Promise.resolve({ id: "p1" }) });
    expect(metadata.title).toBe("Jane Smith | Sunshine Ledger");
  });
});
