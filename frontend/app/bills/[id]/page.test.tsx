import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import BillPage, { generateMetadata } from "./page";
import * as serverApi from "@/lib/server-api";
import type { BillDetail } from "@/lib/types";

vi.mock("@/lib/server-api", () => ({
  getBill: vi.fn(),
}));

const { notFoundMock } = vi.hoisted(() => ({
  notFoundMock: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));
vi.mock("next/navigation", () => ({
  notFound: notFoundMock,
}));

// BillPage is an async Server Component -- no client interactivity, so it
// can be invoked directly as a function (the same thing Next.js does) and
// the resolved element handed to render(), without needing a server runtime.
async function renderBillPage(id = "bill-1") {
  const element = await BillPage({ params: Promise.resolve({ id }) });
  render(element);
}

const baseBill: BillDetail = {
  entity_id: "bill-1",
  bill_number: "HB 123",
  name: "An Act Relating to Something",
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
  source_count: 1,
  full_text_url: "https://example.com/bill",
  primary_sponsor: "Jane Smith",
  last_action: "Referred to committee",
  sponsors: [],
  claims: [],
  news: [],
  votes: [],
};

describe("BillPage", () => {
  beforeEach(() => {
    vi.mocked(serverApi.getBill).mockReset();
    notFoundMock.mockClear();
  });

  it("calls notFound() when the bill doesn't exist", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce(null);
    await expect(renderBillPage("missing")).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFoundMock).toHaveBeenCalled();
  });

  it("renders the core header fields", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce(baseBill);
    await renderBillPage();

    expect(screen.getByRole("heading", { name: "HB 123" })).toBeInTheDocument();
    expect(screen.getByText("An Act Relating to Something")).toBeInTheDocument();
    expect(screen.getByText("FL")).toBeInTheDocument();
    expect(screen.getByText("House")).toBeInTheDocument();
  });

  it("only renders 'What it does' when a summary exists", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce({ ...baseBill, what_it_does: null });
    await renderBillPage();
    expect(screen.queryByText("What it does")).not.toBeInTheDocument();
  });

  it("shows the who-it-affects claim when present, distinct from what-it-does", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce({
      ...baseBill,
      claims: [
        {
          id: "c1",
          claim_type: "who_it_affects",
          claim_text: "Residents of Example County.",
          generated_by: "llm:llama3.1",
          source_count: 1,
          sources: [],
        },
      ],
    });
    await renderBillPage();

    expect(screen.getByText("Who it affects")).toBeInTheDocument();
    expect(screen.getByText("Residents of Example County.")).toBeInTheDocument();
  });

  it("labels co-sponsors distinctly from the primary sponsor", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce({
      ...baseBill,
      sponsors: [
        { entity_id: "p1", name: "Jane Smith", relationship_type: "sponsor" },
        { entity_id: "p2", name: "John Doe", relationship_type: "co_sponsor" },
      ],
    });
    await renderBillPage();

    expect(screen.getByRole("link", { name: "Jane Smith" })).toHaveAttribute("href", "/people/p1");
    expect(screen.getByText(/\(co-sponsor\)/)).toBeInTheDocument();
  });

  it("de-duplicates sources shared across multiple claims", async () => {
    const sharedSource = {
      id: "s1",
      url: "https://example.com/source",
      publisher: "Example Times",
      source_type: "legiscan_bill",
      retrieved_at: "2026-02-01T00:00:00Z",
    };
    vi.mocked(serverApi.getBill).mockResolvedValueOnce({
      ...baseBill,
      claims: [
        { id: "c1", claim_type: "what_it_does", claim_text: "x", generated_by: "llm:x", source_count: 1, sources: [sharedSource] },
        { id: "c2", claim_type: "who_it_affects", claim_text: "y", generated_by: "llm:x", source_count: 1, sources: [sharedSource] },
      ],
    });
    await renderBillPage();

    expect(screen.getAllByText("Example Times")).toHaveLength(1);
  });

  it("shows the AI disclosure with deduplicated model names, but only for LLM-generated claims", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce({
      ...baseBill,
      claims: [
        { id: "c1", claim_type: "what_it_does", claim_text: "x", generated_by: "llm:llama3.1", source_count: 0, sources: [] },
        { id: "c2", claim_type: "who_it_affects", claim_text: "y", generated_by: "llm:llama3.1", source_count: 0, sources: [] },
      ],
    });
    await renderBillPage();

    expect(screen.getByText(/written by an AI model/i)).toBeInTheDocument();
    expect(screen.getAllByText(/llama3\.1/)).toHaveLength(1);
  });

  it("does not show the AI disclosure when every claim was manually reviewed", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce({
      ...baseBill,
      claims: [
        { id: "c1", claim_type: "what_it_does", claim_text: "x", generated_by: "manual_review", source_count: 0, sources: [] },
      ],
    });
    await renderBillPage();

    expect(screen.queryByText(/written by an AI model/i)).not.toBeInTheDocument();
  });

  it("shows roll-call vote tallies and individual votes, with a no-scoring caveat", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce({
      ...baseBill,
      votes: [
        {
          id: "v1",
          roll_call_id: "1644238",
          chamber: "H",
          description: "House: Third Reading RCS#549",
          date: "2026-02-25",
          yea: 82,
          nay: 30,
          nv: 5,
          absent: 0,
          total: 117,
          passed: true,
          source_url: "https://legiscan.com/FL/rollcall/H0033/id/1644238",
          votes: [{ person_entity_id: "p1", person_name: "Jane Smith", vote: "Yea" }],
        },
      ],
    });
    await renderBillPage();

    expect(screen.getByText("House: Third Reading RCS#549")).toBeInTheDocument();
    expect(screen.getByText(/passed 82-30/i)).toBeInTheDocument();
    expect(screen.getByText(/not a score, and not a claim/i)).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "Jane Smith" })).toHaveAttribute("href", "/people/p1");
    expect(screen.getByRole("link", { name: /view roll call/i })).toHaveAttribute(
      "href",
      "https://legiscan.com/FL/rollcall/H0033/id/1644238",
    );
  });

  it("does not render a Votes section when there are no roll calls", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce(baseBill);
    await renderBillPage();
    expect(screen.queryByText("Votes")).not.toBeInTheDocument();
  });

  it("shows news mentions with the unscored caveat when present", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce({
      ...baseBill,
      news: [{ id: "n1", title: "Local paper covers the bill", url: "https://example.com/news", publisher: "The Paper", published_date: "2026-02-01" }],
    });
    await renderBillPage();

    expect(screen.getByText("Local paper covers the bill")).toBeInTheDocument();
    expect(screen.getByText(/not a claim about the bill/i)).toBeInTheDocument();
  });
});

describe("BillPage generateMetadata", () => {
  beforeEach(() => {
    vi.mocked(serverApi.getBill).mockReset();
  });

  it("falls back to a not-found title when the bill doesn't exist", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce(null);
    const metadata = await generateMetadata({ params: Promise.resolve({ id: "missing" }) });
    expect(metadata.title).toBe("Bill not found — Sunshine Ledger");
  });

  it("builds a title and description from the bill's plain-language summary", async () => {
    vi.mocked(serverApi.getBill).mockResolvedValueOnce(baseBill);
    const metadata = await generateMetadata({ params: Promise.resolve({ id: "bill-1" }) });

    expect(metadata.title).toBe("HB 123 — FL | Sunshine Ledger");
    expect(metadata.description).toBe("This bill does a thing.");
  });
});
